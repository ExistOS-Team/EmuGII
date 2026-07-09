import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const qemuCwd = process.env.EMUGII_QEMU_CWD ?? path.join(repoRoot, 'build', 'qemu', 'build');
const qemuBinary = process.env.EMUGII_QEMU_BINARY ?? path.join(
  qemuCwd,
  process.platform === 'win32' ? 'qemu-system-arm.exe' : 'qemu-system-arm',
);

const ICOLL_BASE = 0x80000000;
const DIGCTL_BASE = 0x8001c000;
const PINCTRL_BASE = 0x80018000;
const DFLPT_BASE = 0x800c0000;
const LCDIF_BASE = 0x80030000;
const POWER_BASE = 0x80044000;
const RTC_BASE = 0x8005c000;

class QTestMachine {
  constructor(port) {
    this.buffer = '';
    this.queue = [];
    this.waiters = [];
    this.stderr = '';
    this.proc = spawn(
      qemuBinary,
      [
        '-M', 'stmp3770',
        '-display', 'none',
        '-monitor', 'none',
        '-serial', 'none',
        '-chardev', `socket,id=qtest,host=127.0.0.1,port=${port},server=on,wait=off`,
        '-accel', 'qtest',
        '-qtest', 'chardev:qtest',
      ],
      {
        cwd: qemuCwd,
        stdio: ['ignore', 'ignore', 'pipe'],
        env: process.env,
      },
    );

    this.proc.stderr.setEncoding('utf8');
    this.proc.stderr.on('data', (chunk) => {
      this.stderr += chunk;
    });

    this.socket = new net.Socket();
    this.socket.setEncoding('utf8');
    this.socket.on('data', (chunk) => this.#onStdout(chunk));
  }

  #onStdout(chunk) {
    this.buffer += chunk;
    while (true) {
      const idx = this.buffer.indexOf('\n');
      if (idx === -1) {
        return;
      }
      const line = this.buffer.slice(0, idx).replace(/\r$/, '');
      this.buffer = this.buffer.slice(idx + 1);
      if (!line) {
        continue;
      }
      if (this.waiters.length > 0) {
        const resolve = this.waiters.shift();
        resolve(line);
      } else {
        this.queue.push(line);
      }
    }
  }

  async #readLine(timeoutMs = 5000) {
    if (this.queue.length > 0) {
      return this.queue.shift();
    }

    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const idx = this.waiters.indexOf(done);
        if (idx >= 0) {
          this.waiters.splice(idx, 1);
        }
        reject(new Error(`Timed out waiting for qtest response. stderr=${this.stderr}`));
      }, timeoutMs);

      const done = (line) => {
        clearTimeout(timer);
        resolve(line);
      };

      this.waiters.push(done);
    });
  }

  async connect(timeoutMs = 5000) {
    const deadline = Date.now() + timeoutMs;

    while (true) {
      try {
        await new Promise((resolve, reject) => {
          const onError = (err) => {
            this.socket.off('connect', onConnect);
            reject(err);
          };
          const onConnect = () => {
            this.socket.off('error', onError);
            resolve();
          };

          this.socket.once('error', onError);
          this.socket.once('connect', onConnect);
          this.socket.connect({ host: '127.0.0.1', port: this.port });
        });
        return;
      } catch (err) {
        if (Date.now() >= deadline) {
          throw new Error(`Timed out connecting qtest socket. stderr=${this.stderr}`, { cause: err });
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    }
  }

  async cmd(command) {
    this.socket.write(`${command}\n`);
    while (true) {
      const line = await this.#readLine();
      if (line.startsWith('IRQ ')) {
        continue;
      }
      return line;
    }
  }

  async readl(addr) {
    const resp = await this.cmd(`readl 0x${addr.toString(16)}`);
    assert.match(resp, /^OK 0x[0-9a-fA-F]+$/, `Unexpected readl response: ${resp}`);
    return Number(BigInt(resp.split(' ')[1]));
  }

  async writel(addr, value) {
    const resp = await this.cmd(`writel 0x${addr.toString(16)} 0x${value.toString(16)}`);
    assert.equal(resp, 'OK', `Unexpected writel response: ${resp}`);
  }

  async clockStep(ns) {
    const resp = ns === undefined
      ? await this.cmd('clock_step')
      : await this.cmd(`clock_step ${ns}`);
    assert.match(resp, /^OK /, `Unexpected clock_step response: ${resp}`);
  }

  async close() {
    this.socket.destroy();
    if (this.proc.exitCode !== null) {
      return;
    }
    this.proc.kill('SIGKILL');
    await new Promise((resolve) => {
      this.proc.once('exit', () => resolve());
    });
  }
}

async function reservePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('Failed to reserve TCP port for qtest'));
        return;
      }
      const { port } = address;
      server.close((err) => {
        if (err) {
          reject(err);
        } else {
          resolve(port);
        }
      });
    });
  });
}

async function withMachine(fn) {
  const port = await reservePort();
  const machine = new QTestMachine(port);
  machine.port = port;
  try {
    await machine.connect();
    await fn(machine);
  } finally {
    await machine.close();
  }
}

async function testRtc1MsecIrq() {
  await withMachine(async (machine) => {
    await machine.writel(RTC_BASE + 0x008, 0xc000002d);
    await machine.writel(RTC_BASE + 0x004, 0x00000002);
    await machine.clockStep(1_000_000);

    const ctrl = await machine.readl(RTC_BASE + 0x000);
    const raw0 = await machine.readl(ICOLL_BASE + 0x040);
    const raw1 = await machine.readl(ICOLL_BASE + 0x050);

    assert.notEqual(ctrl & (1 << 3), 0, `RTC 1ms status bit missing: ctrl=0x${ctrl.toString(16)}`);
    assert.equal(raw0 & (1 << 22), 0, `RTC alarm line asserted unexpectedly: raw0=0x${raw0.toString(16)}`);
    assert.notEqual(raw1 & (1 << 16), 0, `RTC 1ms line not asserted on ICOLL source 48: raw1=0x${raw1.toString(16)}`);
  });
}

async function testLcdifCtrl1Layout() {
  await withMachine(async (machine) => {
    await machine.writel(LCDIF_BASE + 0x008, 0xc0000000);
    await machine.writel(LCDIF_BASE + 0x010, 0x00001000);
    await machine.writel(LCDIF_BASE + 0x004, 0x00010000);
    await machine.clockStep(20_000_000);

    const ctrl1 = await machine.readl(LCDIF_BASE + 0x010);
    const raw1 = await machine.readl(ICOLL_BASE + 0x050);

    assert.notEqual(ctrl1 & (1 << 12), 0, `LCDIF VSYNC enable bit lost: ctrl1=0x${ctrl1.toString(16)}`);
    assert.notEqual(ctrl1 & (1 << 8), 0, `LCDIF VSYNC status bit missing from CTRL1: ctrl1=0x${ctrl1.toString(16)}`);
    assert.notEqual(raw1 & (1 << 14), 0, `LCDIF IRQ not asserted on ICOLL source 46: raw1=0x${raw1.toString(16)}`);
  });
}

async function testPinctrlBank3Absent() {
  await withMachine(async (machine) => {
    const ctrl = await machine.readl(PINCTRL_BASE + 0x000);
    const before = await machine.readl(PINCTRL_BASE + 0x430);
    await machine.writel(PINCTRL_BASE + 0x430, 0xffffffff);
    const after = await machine.readl(PINCTRL_BASE + 0x430);

    assert.equal(ctrl & (1 << 29), 0, `PINCTRL PRESENT3 should be 0 on STMP3770: ctrl=0x${ctrl.toString(16)}`);
    assert.equal(before, 0, `Bank 3 DOUT should reset to 0: before=0x${before.toString(16)}`);
    assert.equal(after, 0, `Bank 3 DOUT should remain inactive when GPIO is absent: after=0x${after.toString(16)}`);
  });
}

async function testPowerVersionAndResetContract() {
  await withMachine(async (machine) => {
    const version = await machine.readl(POWER_BASE + 0x110);
    const resetBefore = await machine.readl(POWER_BASE + 0x0e0);

    assert.equal(version, 0x02000000, `POWER VERSION should report v2.0 at 0x110: got 0x${version.toString(16)}`);
    assert.equal(resetBefore, 0, `POWER RESET should reset to 0: got 0x${resetBefore.toString(16)}`);

    await machine.writel(POWER_BASE + 0x0e0, 0x00000001);
    const resetWithoutUnlock = await machine.readl(POWER_BASE + 0x0e0);
    assert.equal(
      resetWithoutUnlock,
      0,
      `POWER RESET low bits must ignore writes without unlock key: got 0x${resetWithoutUnlock.toString(16)}`,
    );

    await machine.writel(POWER_BASE + 0x0e0, 0x3e770001);
    const resetWithUnlock = await machine.readl(POWER_BASE + 0x0e0);
    assert.equal(
      resetWithUnlock,
      0x00000001,
      `POWER RESET should accept unlocked write to PWD bit: got 0x${resetWithUnlock.toString(16)}`,
    );
  });
}

async function testPowerResetValues() {
  await withMachine(async (machine) => {
    const ctrl = await machine.readl(POWER_BASE + 0x000);
    const v5ctrl = await machine.readl(POWER_BASE + 0x010);
    const charge = await machine.readl(POWER_BASE + 0x030);
    const vddd = await machine.readl(POWER_BASE + 0x040);
    const vdda = await machine.readl(POWER_BASE + 0x050);
    const vddio = await machine.readl(POWER_BASE + 0x060);
    const dclimits = await machine.readl(POWER_BASE + 0x090);
    const loopctrl = await machine.readl(POWER_BASE + 0x0a0);
    const speed = await machine.readl(POWER_BASE + 0x0c0);
    const batt = await machine.readl(POWER_BASE + 0x0d0);
    const sts = await machine.readl(POWER_BASE + 0x0b0);

    assert.equal(ctrl, 0x40040024, `POWER CTRL reset mismatch: got 0x${ctrl.toString(16)}`);
    assert.equal(v5ctrl, 0x00000100, `POWER 5VCTRL reset mismatch: got 0x${v5ctrl.toString(16)}`);
    assert.equal(charge, 0x00010000, `POWER CHARGE reset mismatch: got 0x${charge.toString(16)}`);
    assert.equal(vddd, 0x00310710, `POWER VDDDCTRL reset mismatch: got 0x${vddd.toString(16)}`);
    assert.equal(vdda, 0x0000170a, `POWER VDDACTRL reset mismatch: got 0x${vdda.toString(16)}`);
    assert.equal(vddio, 0x0000170c, `POWER VDDIOCTRL reset mismatch: got 0x${vddio.toString(16)}`);
    assert.equal(dclimits, 0x00040c5f, `POWER DCLIMITS reset mismatch: got 0x${dclimits.toString(16)}`);
    assert.equal(loopctrl, 0x00000021, `POWER LOOPCTRL reset mismatch: got 0x${loopctrl.toString(16)}`);
    assert.equal(speed, 0x00000000, `POWER SPEED reset mismatch: got 0x${speed.toString(16)}`);
    assert.equal(batt, 0x00000020, `POWER BATTMONITOR reset mismatch: got 0x${batt.toString(16)}`);
    assert.equal(sts, 0x80000000, `POWER STS reset mismatch: got 0x${sts.toString(16)}`);
  });
}

async function testDflptPte2048Contract() {
  await withMachine(async (machine) => {
    const pte2048 = await machine.readl(DFLPT_BASE + 0x2000);

    assert.equal(
      pte2048,
      0x80000c12,
      `DFLPT PTE_2048 reset mismatch: got 0x${pte2048.toString(16)}`,
    );

    await machine.writel(DFLPT_BASE + 0x2000, 0xffffffff);
    const updated = await machine.readl(DFLPT_BASE + 0x2000);

    assert.equal(
      updated,
      0x80000df6,
      `DFLPT PTE_2048 should only expose AP/DOMAIN/BUFFERABLE fields: got 0x${updated.toString(16)}`,
    );
  });
}

async function testDflptMpteTracksLocator() {
  await withMachine(async (machine) => {
    const mpte0Reset = await machine.readl(DFLPT_BASE + 0x0000);
    const pte5Reset = await machine.readl(DFLPT_BASE + (5 << 2));

    assert.equal(mpte0Reset, 0, `DFLPT MPTE0 reset contents should be 0: got 0x${mpte0Reset.toString(16)}`);
    assert.equal(pte5Reset, 0, `DFLPT unbound PTE5 should reset to 0: got 0x${pte5Reset.toString(16)}`);

    await machine.writel(DFLPT_BASE + 0x0000, 0x11223344);
    const mpte0Written = await machine.readl(DFLPT_BASE + 0x0000);
    assert.equal(mpte0Written, 0x11223344, `DFLPT MPTE0 write should stick at reset locator: got 0x${mpte0Written.toString(16)}`);

    await machine.writel(DIGCTL_BASE + 0x0400, 0x00000020);
    const oldLocation = await machine.readl(DFLPT_BASE + 0x0000);
    const newLocation = await machine.readl(DFLPT_BASE + (0x20 << 2));

    assert.equal(oldLocation, 0, `DFLPT old MPTE0 location should become unbound after locator move: got 0x${oldLocation.toString(16)}`);
    assert.equal(newLocation, 0x11223344, `DFLPT MPTE0 contents should move with DIGCTL_MPTE0_LOC: got 0x${newLocation.toString(16)}`);
  });
}

const tests = [
  ['RTC 1ms IRQ routing', testRtc1MsecIrq],
  ['LCDIF CTRL1 interrupt layout', testLcdifCtrl1Layout],
  ['PINCTRL Bank 3 absence', testPinctrlBank3Absent],
  ['POWER version and reset contract', testPowerVersionAndResetContract],
  ['POWER reset values', testPowerResetValues],
  ['DFLPT PTE_2048 contract', testDflptPte2048Contract],
  ['DFLPT MPTE locator remap', testDflptMpteTracksLocator],
];

let failures = 0;

for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures++;
    console.error(`FAIL ${name}`);
    console.error(err instanceof Error ? err.stack : String(err));
  }
}

if (failures > 0) {
  process.exitCode = 1;
}
