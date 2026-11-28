/* The program of a Mac app that labapp.packaging.mac_app makes (Contents/MacOS/<name>).

It runs Python inside itself: it loads the environment's libpython and runs `python -m <module>`, as
the environment's own python would. The app's program is then this file, part of the app and signed
with it, so macOS names the app in what it says about it: the privacy prompts ("prose would like to
access files in your Desktop folder", not a Python's name) and the permissions it keeps. Built with
today's SDK, it also gives the app the window buttons, title bar and controls of the macOS it runs on
(AppKit draws an app in the design of the SDK its program was built with; conda's Python says 11).

What it runs is in Contents/Resources/launcher.txt, which mac_app writes, one key=value a line:

    python=/opt/anaconda3/envs/prose/bin/python      (Python finds its environment from it; sys.executable)
    libpython=/opt/anaconda3/envs/prose/lib/libpython3.12.dylib
    module=prose

Where libpython can't be loaded (gone with an update to a newer Python, or none written), it runs that
python instead, as the apps did before; macOS then names that Python in its prompts.

Built by tools/make_launcher.py: one program for Apple silicon and Intel Macs, macOS 11 and later. */
#include <dlfcn.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef LAUNCHER_SOURCE
#define LAUNCHER_SOURCE "unknown"
#endif
/* (Which launcher.c this was built from, its SHA-256: labapp's tests check it's the one beside it) */
__attribute__((used)) static const char source[] = "labapp-launcher-source:" LAUNCHER_SOURCE;

#define LINE 4096

static char python[LINE], libpython[LINE], module[LINE];

/* Reads Contents/Resources/launcher.txt, beside this program's folder (Contents/MacOS) */
static int read_config(void) {
    char exe[PATH_MAX], real[PATH_MAX], path[PATH_MAX + 64], line[LINE];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) return 0;
    char *slash = strrchr(real, '/');
    if (!slash) return 0;
    *slash = 0;
    snprintf(path, sizeof path, "%s/../Resources/launcher.txt", real);
    FILE *fh = fopen(path, "r");
    if (!fh) return 0;
    while (fgets(line, sizeof line, fh)) {
        line[strcspn(line, "\r\n")] = 0;
        char *eq = strchr(line, '=');
        if (!eq) continue;
        *eq = 0;
        char *into = !strcmp(line, "python") ? python : !strcmp(line, "libpython") ? libpython
                   : !strcmp(line, "module") ? module : NULL;
        if (into) snprintf(into, LINE, "%s", eq + 1);
    }
    fclose(fh);
    return python[0] && module[0];
}

int main(int argc, char **argv) {
    if (!read_config()) {
        fprintf(stderr, "launcher: no Contents/Resources/launcher.txt saying which Python and module to run\n");
        return 70;
    }
    /* python -m <module>, then what the app was given */
    char **args = calloc((size_t)argc + 3, sizeof *args);
    if (!args) return 71;
    int n = 0;
    args[n++] = python;
    args[n++] = "-m";
    args[n++] = module;
    for (int i = 1; i < argc; i++) args[n++] = argv[i];
    args[n] = NULL;
    if (libpython[0]) {
        /* (RTLD_GLOBAL: the environment's extension modules look for Python's functions in the program) */
        void *lib = dlopen(libpython, RTLD_NOW | RTLD_GLOBAL);
        int (*bytes_main)(int, char **) = lib ? (int (*)(int, char **))dlsym(lib, "Py_BytesMain") : NULL;
        if (bytes_main) return bytes_main(n, args);
        fprintf(stderr, "launcher: couldn't load Python from %s (%s); running %s instead\n",
                libpython, lib ? "no Py_BytesMain" : dlerror(), python);
    }
    execv(python, args);
    fprintf(stderr, "launcher: couldn't run %s\n", python);
    return 72;
}
