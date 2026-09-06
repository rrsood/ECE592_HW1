#define _GNU_SOURCE

#include "metadata.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <sched.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#ifndef ECE592_BUILD_FLAGS
#define ECE592_BUILD_FLAGS "not-supplied"
#endif

#ifndef ECE592_GIT_COMMIT
#define ECE592_GIT_COMMIT "not-supplied"
#endif

static int copy_text(char *destination, size_t capacity, const char *source)
{
    int written;

    written = snprintf(destination, capacity, "%s", source);
    if (written < 0 || (size_t)written >= capacity) {
        errno = ENAMETOOLONG;
        return -1;
    }

    return 0;
}

static char *trim_space(char *text)
{
    char *end;

    while (isspace((unsigned char)*text) != 0) {
        ++text;
    }

    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1]) != 0) {
        --end;
    }
    *end = '\0';

    return text;
}

static int read_cpu_model(char *destination, size_t capacity,
                          char *source, size_t source_capacity)
{
    FILE *stream;
    char line[512];
    char implementer[32] = "";
    char architecture[32] = "";
    char variant[32] = "";
    char part[32] = "";
    char revision[32] = "";
    int best_priority = 0;

    stream = fopen("/proc/cpuinfo", "r");
    if (stream == NULL) {
        return -1;
    }

    while (fgets(line, sizeof(line), stream) != NULL) {
        char *colon = strchr(line, ':');
        char *key;
        char *value;
        int priority = 0;

        if (colon == NULL) {
            continue;
        }

        *colon = '\0';
        key = trim_space(line);
        value = trim_space(colon + 1);

        if (strcmp(key, "model name") == 0) {
            priority = 3;
        } else if (strcmp(key, "Hardware") == 0) {
            priority = 2;
        } else if (strcmp(key, "Processor") == 0) {
            priority = 1;
        }

        if (strcmp(key, "CPU implementer") == 0 && implementer[0] == '\0') {
            if (copy_text(implementer, sizeof(implementer), value) != 0) {
                (void)fclose(stream);
                return -1;
            }
        } else if (strcmp(key, "CPU architecture") == 0 &&
                   architecture[0] == '\0') {
            if (copy_text(architecture, sizeof(architecture), value) != 0) {
                (void)fclose(stream);
                return -1;
            }
        } else if (strcmp(key, "CPU variant") == 0 && variant[0] == '\0') {
            if (copy_text(variant, sizeof(variant), value) != 0) {
                (void)fclose(stream);
                return -1;
            }
        } else if (strcmp(key, "CPU part") == 0 && part[0] == '\0') {
            if (copy_text(part, sizeof(part), value) != 0) {
                (void)fclose(stream);
                return -1;
            }
        } else if (strcmp(key, "CPU revision") == 0 && revision[0] == '\0') {
            if (copy_text(revision, sizeof(revision), value) != 0) {
                (void)fclose(stream);
                return -1;
            }
        }

        if (priority > best_priority && value[0] != '\0') {
            if (copy_text(destination, capacity, value) != 0) {
                (void)fclose(stream);
                return -1;
            }
            best_priority = priority;
        }
    }

    if (ferror(stream) != 0) {
        (void)fclose(stream);
        return -1;
    }
    if (fclose(stream) != 0) {
        return -1;
    }
    if (best_priority > 0) {
        return copy_text(source, source_capacity,
                         "/proc/cpuinfo human-readable field");
    }

    if (implementer[0] != '\0' && part[0] != '\0') {
        int written;

        written = snprintf(destination, capacity,
                           "AArch64 implementer=%s architecture=%s "
                           "variant=%s part=%s revision=%s",
                           implementer,
                           architecture[0] == '\0' ? "unavailable" : architecture,
                           variant[0] == '\0' ? "unavailable" : variant,
                           part,
                           revision[0] == '\0' ? "unavailable" : revision);
        if (written < 0 || (size_t)written >= capacity) {
            errno = ENAMETOOLONG;
            return -1;
        }

        return copy_text(source, source_capacity,
                         "/proc/cpuinfo AArch64 identification fields");
    }

    errno = ENODATA;
    return -1;
}

static int make_cpu_path(char *path, size_t capacity, int logical_cpu,
                         const char *suffix)
{
    int written;

    written = snprintf(path, capacity, "/sys/devices/system/cpu/cpu%d/%s",
                       logical_cpu, suffix);
    if (written < 0 || (size_t)written >= capacity) {
        errno = ENAMETOOLONG;
        return -1;
    }

    return 0;
}

static int read_line_file(const char *path, char *destination, size_t capacity)
{
    FILE *stream;

    stream = fopen(path, "r");
    if (stream == NULL) {
        return -1;
    }

    if (fgets(destination, (int)capacity, stream) == NULL) {
        (void)fclose(stream);
        errno = EIO;
        return -1;
    }

    if (fclose(stream) != 0) {
        return -1;
    }

    (void)trim_space(destination);
    return 0;
}

static int read_int_file(const char *path, int *value)
{
    FILE *stream;
    int parsed_value;
    int trailing_character;

    stream = fopen(path, "r");
    if (stream == NULL) {
        return -1;
    }

    if (fscanf(stream, "%d", &parsed_value) != 1) {
        (void)fclose(stream);
        errno = EIO;
        return -1;
    }

    do {
        trailing_character = fgetc(stream);
    } while (trailing_character != EOF &&
             isspace((unsigned char)trailing_character) != 0);

    if (trailing_character != EOF) {
        (void)fclose(stream);
        errno = EIO;
        return -1;
    }
    if (fclose(stream) != 0) {
        return -1;
    }

    *value = parsed_value;
    return 0;
}

static int find_numa_node(int logical_cpu, int *numa_node)
{
    char path[PATH_MAX];
    DIR *directory;
    struct dirent *entry;

    if (make_cpu_path(path, sizeof(path), logical_cpu, "") != 0) {
        return -1;
    }

    directory = opendir(path);
    if (directory == NULL) {
        return -1;
    }

    while ((entry = readdir(directory)) != NULL) {
        char *end;
        long node;

        if (strncmp(entry->d_name, "node", 4) != 0 ||
            isdigit((unsigned char)entry->d_name[4]) == 0) {
            continue;
        }

        errno = 0;
        end = NULL;
        node = strtol(entry->d_name + 4, &end, 10);
        if (errno == 0 && *end == '\0' && node >= 0 && node <= INT_MAX) {
            *numa_node = (int)node;
            (void)closedir(directory);
            return 0;
        }
    }

    (void)closedir(directory);
    errno = ENODATA;
    return -1;
}

static int read_affinity(struct system_metadata *metadata)
{
    cpu_set_t allowed_set;
    size_t used = 0u;

    if (sched_getaffinity(0, sizeof(allowed_set), &allowed_set) != 0) {
        return -1;
    }

    metadata->affinity_allowed_cpu_count = CPU_COUNT(&allowed_set);
    metadata->affinity_cpu_list[0] = '\0';

    for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu) {
        int written;

        if (!CPU_ISSET(cpu, &allowed_set)) {
            continue;
        }

        written = snprintf(metadata->affinity_cpu_list + used,
                           sizeof(metadata->affinity_cpu_list) - used,
                           "%s%d", used == 0u ? "" : ",", cpu);
        if (written < 0 ||
            (size_t)written >= sizeof(metadata->affinity_cpu_list) - used) {
            errno = ENAMETOOLONG;
            return -1;
        }
        used += (size_t)written;
    }

    if (metadata->affinity_allowed_cpu_count <= 0) {
        errno = ENODATA;
        return -1;
    }

    return 0;
}

static int read_timestamp_utc(char *destination, size_t capacity)
{
    struct tm broken_down;
    time_t now;

    now = time(NULL);
    if (now == (time_t)-1 || gmtime_r(&now, &broken_down) == NULL) {
        return -1;
    }

    if (strftime(destination, capacity, "%Y-%m-%dT%H:%M:%SZ",
                 &broken_down) == 0u) {
        errno = EOVERFLOW;
        return -1;
    }

    return 0;
}

int metadata_collect(struct system_metadata *metadata)
{
    struct utsname system_name;
    char path[PATH_MAX];

    if (metadata == NULL) {
        errno = EINVAL;
        return -1;
    }

    memset(metadata, 0, sizeof(*metadata));

    if (read_timestamp_utc(metadata->timestamp_utc,
                           sizeof(metadata->timestamp_utc)) != 0 ||
        uname(&system_name) != 0 ||
        copy_text(metadata->hostname, sizeof(metadata->hostname),
                  system_name.nodename) != 0 ||
        copy_text(metadata->kernel_release, sizeof(metadata->kernel_release),
                  system_name.release) != 0 ||
        copy_text(metadata->isa, sizeof(metadata->isa),
                  system_name.machine) != 0 ||
        read_cpu_model(metadata->cpu_model, sizeof(metadata->cpu_model),
                       metadata->cpu_model_source,
                       sizeof(metadata->cpu_model_source)) != 0) {
        return -1;
    }

    metadata->page_size_bytes = sysconf(_SC_PAGESIZE);
    metadata->logical_cpu = sched_getcpu();
    if (metadata->page_size_bytes <= 0 || metadata->logical_cpu < 0) {
        return -1;
    }

    if (read_affinity(metadata) != 0) {
        return -1;
    }

    if (make_cpu_path(path, sizeof(path), metadata->logical_cpu,
                      "topology/core_id") != 0 ||
        read_int_file(path, &metadata->physical_core_id) != 0 ||
        make_cpu_path(path, sizeof(path), metadata->logical_cpu,
                      "topology/physical_package_id") != 0 ||
        read_int_file(path, &metadata->physical_package_id) != 0 ||
        make_cpu_path(path, sizeof(path), metadata->logical_cpu,
                      "topology/thread_siblings_list") != 0 ||
        read_line_file(path, metadata->thread_siblings_list,
                       sizeof(metadata->thread_siblings_list)) != 0 ||
        find_numa_node(metadata->logical_cpu, &metadata->numa_node) != 0) {
        return -1;
    }

    return 0;
}

int metadata_write(FILE *stream, const struct system_metadata *metadata)
{
    if (stream == NULL || metadata == NULL) {
        errno = EINVAL;
        return -1;
    }

    if (fprintf(stream, "timestamp_utc=%s\n", metadata->timestamp_utc) < 0 ||
        fprintf(stream, "hostname=%s\n", metadata->hostname) < 0 ||
        fprintf(stream, "kernel_release=%s\n", metadata->kernel_release) < 0 ||
        fprintf(stream, "isa=%s\n", metadata->isa) < 0 ||
        fprintf(stream, "cpu_model=%s\n", metadata->cpu_model) < 0 ||
        fprintf(stream, "cpu_model_source=%s\n",
                metadata->cpu_model_source) < 0 ||
        fprintf(stream, "page_size_bytes=%ld\n", metadata->page_size_bytes) < 0 ||
        fprintf(stream, "logical_cpu=%d\n", metadata->logical_cpu) < 0 ||
        fprintf(stream, "affinity_cpu_list=%s\n",
                metadata->affinity_cpu_list) < 0 ||
        fprintf(stream, "affinity_allowed_cpu_count=%d\n",
                metadata->affinity_allowed_cpu_count) < 0 ||
        fprintf(stream, "physical_core_id=%d\n",
                metadata->physical_core_id) < 0 ||
        fprintf(stream, "physical_package_id=%d\n",
                metadata->physical_package_id) < 0 ||
        fprintf(stream,
                "topology_id_source=Linux sysfs physical topology IDs\n") < 0 ||
        fprintf(stream, "numa_node=%d\n", metadata->numa_node) < 0 ||
        fprintf(stream, "thread_siblings_list=%s\n",
                metadata->thread_siblings_list) < 0 ||
        fprintf(stream, "compiler_version=%s\n", __VERSION__) < 0 ||
        fprintf(stream, "compiler_flags=%s\n", ECE592_BUILD_FLAGS) < 0 ||
        fprintf(stream, "git_commit=%s\n", ECE592_GIT_COMMIT) < 0) {
        return -1;
    }

    return 0;
}

#if defined(ECE592_METADATA_SELF_TEST)

#include "affinity.h"

int main(int argc, char **argv)
{
    struct affinity_info affinity;
    struct system_metadata metadata;
    char *end;
    long logical_cpu;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <logical-cpu>\n", argv[0]);
        return 2;
    }

    errno = 0;
    end = NULL;
    logical_cpu = strtol(argv[1], &end, 10);
    if (errno != 0 || end == argv[1] || *end != '\0' ||
        logical_cpu < 0 || logical_cpu > INT_MAX) {
        fprintf(stderr, "error: invalid logical CPU: %s\n", argv[1]);
        return 2;
    }

    if (affinity_pin_current_thread((int)logical_cpu, &affinity) != 0) {
        perror("affinity_pin_current_thread");
        return 1;
    }
    if (metadata_collect(&metadata) != 0) {
        perror("metadata_collect");
        return 1;
    }
    if (metadata_write(stdout, &metadata) != 0) {
        perror("metadata_write");
        return 1;
    }

    if (affinity.allowed_cpu_count != metadata.affinity_allowed_cpu_count) {
        fprintf(stderr, "error: affinity verification changed unexpectedly\n");
        return 1;
    }
    printf("smt_siblings_idle=not-verified-by-this-test\n");
    printf("status=ok\n");
    return 0;
}

#endif
