#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>

static int quote_arg(const wchar_t *arg, wchar_t *out, size_t out_len)
{
    size_t used = 0;
    size_t slash_count;
    BOOL need_quotes = !arg[0] || wcspbrk(arg, L" \t\n\v\"");

#define APPEND_CH(ch) do { \
    if (used + 1 >= out_len) { \
        return 0; \
    } \
    out[used++] = (ch); \
} while (0)

    if (!need_quotes) {
        size_t len = wcslen(arg);
        if (len >= out_len) {
            return 0;
        }
        wcscpy(out, arg);
        return 1;
    }

    APPEND_CH(L'"');
    while (*arg) {
        slash_count = 0;
        while (*arg == L'\\') {
            slash_count++;
            arg++;
        }
        if (*arg == L'"') {
            while (slash_count--) {
                APPEND_CH(L'\\');
                APPEND_CH(L'\\');
            }
            APPEND_CH(L'\\');
            APPEND_CH(*arg++);
            continue;
        }
        if (!*arg) {
            while (slash_count--) {
                APPEND_CH(L'\\');
                APPEND_CH(L'\\');
            }
            break;
        }
        while (slash_count--) {
            APPEND_CH(L'\\');
        }
        APPEND_CH(*arg++);
    }
    APPEND_CH(L'"');
    out[used] = L'\0';
    return 1;

#undef APPEND_CH
}

static int append_arg(wchar_t *cmdline, size_t cmdline_len, const wchar_t *arg)
{
    wchar_t quoted[32768];
    size_t used = wcslen(cmdline);
    size_t len;

    if (!quote_arg(arg, quoted, sizeof(quoted) / sizeof(quoted[0]))) {
        return 0;
    }

    len = wcslen(quoted);
    if (used && used + 1 < cmdline_len) {
        cmdline[used++] = L' ';
        cmdline[used] = L'\0';
    }
    if (used + len >= cmdline_len) {
        return 0;
    }
    wcscpy(cmdline + used, quoted);
    return 1;
}

int wmain(void)
{
    wchar_t launcher_path[MAX_PATH];
    wchar_t root_dir[MAX_PATH];
    wchar_t bin_dir[MAX_PATH];
    wchar_t runtime_path[MAX_PATH];
    wchar_t cmdline[32768] = L"";
    int argc = 0;
    LPWSTR *argv;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    DWORD exit_code;

    if (!GetModuleFileNameW(NULL, launcher_path, MAX_PATH)) {
        fwprintf(stderr, L"EmuGii launcher: failed to locate executable\n");
        return 1;
    }

    wcscpy(root_dir, launcher_path);
    wchar_t *slash = wcsrchr(root_dir, L'\\');
    if (!slash) {
        fwprintf(stderr, L"EmuGii launcher: invalid executable path\n");
        return 1;
    }
    *slash = L'\0';

    if (swprintf(bin_dir, MAX_PATH, L"%ls\\bin", root_dir) < 0 ||
        swprintf(runtime_path, MAX_PATH, L"%ls\\EmuGii-runtime.exe", bin_dir) < 0) {
        fwprintf(stderr, L"EmuGii launcher: path is too long\n");
        return 1;
    }

    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS |
                             LOAD_LIBRARY_SEARCH_USER_DIRS);
    AddDllDirectory(bin_dir);

    if (!append_arg(cmdline, sizeof(cmdline) / sizeof(cmdline[0]),
                    runtime_path)) {
        fwprintf(stderr, L"EmuGii launcher: command line is too long\n");
        return 1;
    }

    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) {
        fwprintf(stderr, L"EmuGii launcher: failed to parse arguments\n");
        return 1;
    }
    for (int i = 1; i < argc; i++) {
        if (!append_arg(cmdline, sizeof(cmdline) / sizeof(cmdline[0]), argv[i])) {
            LocalFree(argv);
            fwprintf(stderr, L"EmuGii launcher: command line is too long\n");
            return 1;
        }
    }
    LocalFree(argv);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(runtime_path, cmdline, NULL, NULL, TRUE, 0, NULL,
                        bin_dir, &si, &pi)) {
        fwprintf(stderr, L"EmuGii launcher: failed to start %ls (%lu)\n",
                 runtime_path, GetLastError());
        return 1;
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        exit_code = 1;
    }
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (int)exit_code;
}
