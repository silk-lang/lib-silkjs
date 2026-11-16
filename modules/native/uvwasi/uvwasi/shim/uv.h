/* uv.h for uvwasi without libuv.
 *
 * uvwasi (../src, ../include) is written against libuv. This header declares the part of libuv's
 * interface that uvwasi uses and nothing else, and no libuv C is compiled: the functions are
 * implemented in Silk, in the runtime's src/ext/uvwasi_host.silk, under silk_uvwasi_* symbols.
 * Each uv_* function name below is a macro for, or a static inline wrapper of, its silk_uvwasi_*
 * symbol, so no object file defines or references a symbol named uv_*.
 *
 * The type layouts are this header's own, not libuv's. uvwasi_host.silk declares the same
 * layouts as `extern "C" struct`s. The _Static_asserts at the end of this file state the sizes
 * and offsets that the Silk side assumes, and layoutsAgree in uvwasi_host.silk checks its side
 * when the first request or loop is made. Change both files together.
 *
 * The error constants follow libuv 1.51's include/uv/errno.h: the negated errno of the platform
 * where it has one, and libuv's fixed fallback number where it has not. The handle type, dirent
 * type, poll event and run mode numbers are libuv's as well. libuv is MIT licensed, Copyright
 * Joyent, Inc. and other Node contributors.
 */
#ifndef SILK_UVWASI_UV_H_
#define SILK_UVWASI_UV_H_

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <dirent.h>
#include <pthread.h>
#include <signal.h>
#include <unistd.h>
/* The rest of what libuv's uv.h, uv/unix.h and uv/darwin.h include, which uvwasi's sources rely on
 * (clocks.c uses Mach's thread_info through them on Darwin). */
#include <math.h>
#include <netinet/tcp.h>
#include <netdb.h>
#include <termios.h>
#include <pwd.h>
#include <semaphore.h>
#include <sys/param.h>
#if defined(__APPLE__)
# include <mach/mach.h>
# include <mach/task.h>
# include <mach/semaphore.h>
# include <TargetConditionals.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Errors. */

#define UV__EOF     (-4095)
#define UV__UNKNOWN (-4094)
#define UV_EOF      UV__EOF
#define UV_UNKNOWN  UV__UNKNOWN

#ifdef E2BIG
# define UV_E2BIG (-E2BIG)
#else
# define UV_E2BIG (-4093)
#endif
#ifdef EACCES
# define UV_EACCES (-EACCES)
#else
# define UV_EACCES (-4092)
#endif
#ifdef EADDRINUSE
# define UV_EADDRINUSE (-EADDRINUSE)
#else
# define UV_EADDRINUSE (-4091)
#endif
#ifdef EADDRNOTAVAIL
# define UV_EADDRNOTAVAIL (-EADDRNOTAVAIL)
#else
# define UV_EADDRNOTAVAIL (-4090)
#endif
#ifdef EAFNOSUPPORT
# define UV_EAFNOSUPPORT (-EAFNOSUPPORT)
#else
# define UV_EAFNOSUPPORT (-4089)
#endif
#ifdef EAGAIN
# define UV_EAGAIN (-EAGAIN)
#else
# define UV_EAGAIN (-4088)
#endif
#ifdef EALREADY
# define UV_EALREADY (-EALREADY)
#else
# define UV_EALREADY (-4084)
#endif
#ifdef EBADF
# define UV_EBADF (-EBADF)
#else
# define UV_EBADF (-4083)
#endif
#ifdef EBUSY
# define UV_EBUSY (-EBUSY)
#else
# define UV_EBUSY (-4082)
#endif
#ifdef ECANCELED
# define UV_ECANCELED (-ECANCELED)
#else
# define UV_ECANCELED (-4081)
#endif
#ifdef ECONNABORTED
# define UV_ECONNABORTED (-ECONNABORTED)
#else
# define UV_ECONNABORTED (-4079)
#endif
#ifdef ECONNREFUSED
# define UV_ECONNREFUSED (-ECONNREFUSED)
#else
# define UV_ECONNREFUSED (-4078)
#endif
#ifdef ECONNRESET
# define UV_ECONNRESET (-ECONNRESET)
#else
# define UV_ECONNRESET (-4077)
#endif
#ifdef EDESTADDRREQ
# define UV_EDESTADDRREQ (-EDESTADDRREQ)
#else
# define UV_EDESTADDRREQ (-4076)
#endif
#ifdef EEXIST
# define UV_EEXIST (-EEXIST)
#else
# define UV_EEXIST (-4075)
#endif
#ifdef EFAULT
# define UV_EFAULT (-EFAULT)
#else
# define UV_EFAULT (-4074)
#endif
#ifdef EFBIG
# define UV_EFBIG (-EFBIG)
#else
# define UV_EFBIG (-4036)
#endif
#ifdef EHOSTUNREACH
# define UV_EHOSTUNREACH (-EHOSTUNREACH)
#else
# define UV_EHOSTUNREACH (-4073)
#endif
#ifdef EINTR
# define UV_EINTR (-EINTR)
#else
# define UV_EINTR (-4072)
#endif
#ifdef EINVAL
# define UV_EINVAL (-EINVAL)
#else
# define UV_EINVAL (-4071)
#endif
#ifdef EIO
# define UV_EIO (-EIO)
#else
# define UV_EIO (-4070)
#endif
#ifdef EISCONN
# define UV_EISCONN (-EISCONN)
#else
# define UV_EISCONN (-4069)
#endif
#ifdef EISDIR
# define UV_EISDIR (-EISDIR)
#else
# define UV_EISDIR (-4068)
#endif
#ifdef ELOOP
# define UV_ELOOP (-ELOOP)
#else
# define UV_ELOOP (-4067)
#endif
#ifdef EMFILE
# define UV_EMFILE (-EMFILE)
#else
# define UV_EMFILE (-4066)
#endif
#ifdef EMLINK
# define UV_EMLINK (-EMLINK)
#else
# define UV_EMLINK (-4032)
#endif
#ifdef EMSGSIZE
# define UV_EMSGSIZE (-EMSGSIZE)
#else
# define UV_EMSGSIZE (-4065)
#endif
#ifdef ENAMETOOLONG
# define UV_ENAMETOOLONG (-ENAMETOOLONG)
#else
# define UV_ENAMETOOLONG (-4064)
#endif
#ifdef ENETDOWN
# define UV_ENETDOWN (-ENETDOWN)
#else
# define UV_ENETDOWN (-4063)
#endif
#ifdef ENETUNREACH
# define UV_ENETUNREACH (-ENETUNREACH)
#else
# define UV_ENETUNREACH (-4062)
#endif
#ifdef ENFILE
# define UV_ENFILE (-ENFILE)
#else
# define UV_ENFILE (-4061)
#endif
#ifdef ENOBUFS
# define UV_ENOBUFS (-ENOBUFS)
#else
# define UV_ENOBUFS (-4060)
#endif
#ifdef ENODEV
# define UV_ENODEV (-ENODEV)
#else
# define UV_ENODEV (-4059)
#endif
#ifdef ENOENT
# define UV_ENOENT (-ENOENT)
#else
# define UV_ENOENT (-4058)
#endif
#ifdef ENOMEM
# define UV_ENOMEM (-ENOMEM)
#else
# define UV_ENOMEM (-4057)
#endif
#ifdef ENONET
# define UV_ENONET (-ENONET)
#else
# define UV_ENONET (-4056)
#endif
#ifdef ENOPROTOOPT
# define UV_ENOPROTOOPT (-ENOPROTOOPT)
#else
# define UV_ENOPROTOOPT (-4035)
#endif
#ifdef ENOSPC
# define UV_ENOSPC (-ENOSPC)
#else
# define UV_ENOSPC (-4055)
#endif
#ifdef ENOSYS
# define UV_ENOSYS (-ENOSYS)
#else
# define UV_ENOSYS (-4054)
#endif
#ifdef ENOTCONN
# define UV_ENOTCONN (-ENOTCONN)
#else
# define UV_ENOTCONN (-4053)
#endif
#ifdef ENOTDIR
# define UV_ENOTDIR (-ENOTDIR)
#else
# define UV_ENOTDIR (-4052)
#endif
#ifdef ENOTEMPTY
# define UV_ENOTEMPTY (-ENOTEMPTY)
#else
# define UV_ENOTEMPTY (-4051)
#endif
#ifdef ENOTSOCK
# define UV_ENOTSOCK (-ENOTSOCK)
#else
# define UV_ENOTSOCK (-4050)
#endif
#ifdef ENOTSUP
# define UV_ENOTSUP (-ENOTSUP)
#else
# define UV_ENOTSUP (-4049)
#endif
#ifdef ENXIO
# define UV_ENXIO (-ENXIO)
#else
# define UV_ENXIO (-4033)
#endif
#ifdef EPERM
# define UV_EPERM (-EPERM)
#else
# define UV_EPERM (-4048)
#endif
#ifdef EPIPE
# define UV_EPIPE (-EPIPE)
#else
# define UV_EPIPE (-4047)
#endif
#ifdef EPROTO
# define UV_EPROTO (-EPROTO)
#else
# define UV_EPROTO (-4046)
#endif
#ifdef EPROTONOSUPPORT
# define UV_EPROTONOSUPPORT (-EPROTONOSUPPORT)
#else
# define UV_EPROTONOSUPPORT (-4045)
#endif
#ifdef EPROTOTYPE
# define UV_EPROTOTYPE (-EPROTOTYPE)
#else
# define UV_EPROTOTYPE (-4044)
#endif
#ifdef ERANGE
# define UV_ERANGE (-ERANGE)
#else
# define UV_ERANGE (-4034)
#endif
#ifdef EROFS
# define UV_EROFS (-EROFS)
#else
# define UV_EROFS (-4043)
#endif
#ifdef ESHUTDOWN
# define UV_ESHUTDOWN (-ESHUTDOWN)
#else
# define UV_ESHUTDOWN (-4042)
#endif
#ifdef ESPIPE
# define UV_ESPIPE (-ESPIPE)
#else
# define UV_ESPIPE (-4041)
#endif
#ifdef ESRCH
# define UV_ESRCH (-ESRCH)
#else
# define UV_ESRCH (-4040)
#endif
#ifdef ETIMEDOUT
# define UV_ETIMEDOUT (-ETIMEDOUT)
#else
# define UV_ETIMEDOUT (-4039)
#endif
#ifdef ETXTBSY
# define UV_ETXTBSY (-ETXTBSY)
#else
# define UV_ETXTBSY (-4038)
#endif
#ifdef EXDEV
# define UV_EXDEV (-EXDEV)
#else
# define UV_EXDEV (-4037)
#endif

/* Constants. */

typedef enum {
  UV_UNKNOWN_HANDLE = 0,
  UV_ASYNC,
  UV_CHECK,
  UV_FS_EVENT,
  UV_FS_POLL,
  UV_HANDLE,
  UV_IDLE,
  UV_NAMED_PIPE,
  UV_POLL,
  UV_PREPARE,
  UV_PROCESS,
  UV_STREAM,
  UV_TCP,
  UV_TIMER,
  UV_TTY,
  UV_UDP,
  UV_SIGNAL,
  UV_FILE,
  UV_HANDLE_TYPE_MAX
} uv_handle_type;

typedef enum {
  UV_RUN_DEFAULT = 0,
  UV_RUN_ONCE,
  UV_RUN_NOWAIT
} uv_run_mode;

enum uv_poll_event {
  UV_READABLE = 1,
  UV_WRITABLE = 2,
  UV_DISCONNECT = 4,
  UV_PRIORITIZED = 8
};

typedef enum {
  UV_DIRENT_UNKNOWN,
  UV_DIRENT_FILE,
  UV_DIRENT_DIR,
  UV_DIRENT_LINK,
  UV_DIRENT_FIFO,
  UV_DIRENT_SOCKET,
  UV_DIRENT_CHAR,
  UV_DIRENT_BLOCK
} uv_dirent_type_t;

#define UV_FS_O_APPEND    O_APPEND
#define UV_FS_O_CREAT     O_CREAT
#define UV_FS_O_DIRECTORY O_DIRECTORY
#define UV_FS_O_DSYNC     O_DSYNC
#define UV_FS_O_EXCL      O_EXCL
#define UV_FS_O_NONBLOCK  O_NONBLOCK
#define UV_FS_O_RDONLY    O_RDONLY
#define UV_FS_O_RDWR      O_RDWR
#define UV_FS_O_SYNC      O_SYNC
#define UV_FS_O_TRUNC     O_TRUNC
#define UV_FS_O_WRONLY    O_WRONLY

/* Types. */

typedef int uv_file;
typedef pthread_mutex_t uv_mutex_t;
typedef pthread_rwlock_t uv_rwlock_t;

typedef struct uv_loop_s uv_loop_t;
typedef struct uv_handle_s uv_handle_t;
typedef struct uv_poll_s uv_poll_t;
typedef struct uv_timer_s uv_timer_t;
/* One struct serves both names: uvwasi casts freely between them. */
typedef struct uv_stream_s uv_stream_t;
typedef struct uv_stream_s uv_tcp_t;
typedef struct uv_shutdown_s uv_shutdown_t;
typedef struct uv_fs_s uv_fs_t;
typedef struct uv_dir_s uv_dir_t;
typedef struct uv_dirent_s uv_dirent_t;

typedef struct uv_buf_t {
  char* base;
  size_t len;
} uv_buf_t;

typedef struct {
  long tv_sec;
  long tv_nsec;
} uv_timespec_t;

typedef struct {
  int64_t tv_sec;
  int32_t tv_usec;
} uv_timeval64_t;

typedef struct {
  uint64_t st_dev;
  uint64_t st_mode;
  uint64_t st_nlink;
  uint64_t st_uid;
  uint64_t st_gid;
  uint64_t st_rdev;
  uint64_t st_ino;
  uint64_t st_size;
  uint64_t st_blksize;
  uint64_t st_blocks;
  uint64_t st_flags;
  uint64_t st_gen;
  uv_timespec_t st_atim;
  uv_timespec_t st_mtim;
  uv_timespec_t st_ctim;
  uv_timespec_t st_birthtim;
} uv_stat_t;

typedef void (*uv_alloc_cb)(uv_handle_t* handle, size_t suggested_size, uv_buf_t* buf);
typedef void (*uv_read_cb)(uv_stream_t* stream, ssize_t nread, const uv_buf_t* buf);
typedef void (*uv_shutdown_cb)(uv_shutdown_t* req, int status);
typedef void (*uv_connection_cb)(uv_stream_t* server, int status);
typedef void (*uv_close_cb)(uv_handle_t* handle);
typedef void (*uv_poll_cb)(uv_poll_t* handle, int status, int events);
typedef void (*uv_timer_cb)(uv_timer_t* handle);
typedef void (*uv_fs_cb)(uv_fs_t* req);
typedef void (*uv_random_cb)(void* req, int status, void* buf, size_t buflen);

/* A loop private to uvwasi: poll_oneoff makes one for each call, and uvwasi_init makes one when
 * it is given sockets to open. It is not the runtime's event loop. */
struct uv_loop_s {
  void* data;
  uv_handle_t* handles;          /* Every handle that is active, holds a descriptor, or closes. */
  uv_handle_t* closing_handles;
  uint64_t time;                 /* Milliseconds of the monotonic clock, as of the last update. */
  unsigned int active_handles;   /* Handles that are both active and referenced. */
  unsigned int active_reqs;      /* Shutdown requests waiting for the next turn. */
  int stop_flag;
  int reserved;
};

#define SILK_UVWASI_HANDLE_FIELDS                                             \
  void* data;                                                                 \
  uv_loop_t* loop;                                                            \
  uv_handle_type type;                                                        \
  unsigned int flags;                                                         \
  uv_close_cb close_cb;                                                       \
  uv_handle_t* next;                                                          \
  uv_handle_t* prev;                                                          \
  uv_handle_t* next_closing;

struct uv_handle_s {
  SILK_UVWASI_HANDLE_FIELDS
};

struct uv_poll_s {
  SILK_UVWASI_HANDLE_FIELDS
  uv_poll_cb poll_cb;
  int fd;
  int events;                    /* The poll(2) events asked for; 0 while stopped. */
};

struct uv_timer_s {
  SILK_UVWASI_HANDLE_FIELDS
  uv_timer_cb timer_cb;
  uint64_t timeout;              /* The loop time at which it is due. */
  uint64_t repeat;
};

struct uv_stream_s {
  SILK_UVWASI_HANDLE_FIELDS
  uv_alloc_cb alloc_cb;
  uv_read_cb read_cb;
  uv_connection_cb connection_cb;
  uv_shutdown_t* shutdown_req;
  int fd;
  int accepted_fd;
  int delayed_error;
  int reserved;
};

struct uv_shutdown_s {
  void* data;
  uv_stream_t* handle;
  uv_shutdown_cb cb;
};

struct uv_fs_s {
  ssize_t result;
  void* ptr;
  int fs_type;                   /* What the request was, which says who owns ptr. */
  int reserved;
  uv_stat_t statbuf;
};

struct uv_dirent_s {
  const char* name;
  uv_dirent_type_t type;
};

struct uv_dir_s {
  uv_dirent_t* dirents;
  size_t nentries;
  void* dir;                     /* The DIR*. */
};

/* Functions. Each is a symbol that src/ext/uvwasi_host.silk exports. */

#define uv_translate_sys_error silk_uvwasi_translate_sys_error
#define uv_hrtime silk_uvwasi_hrtime
#define uv_gettimeofday silk_uvwasi_gettimeofday
#define uv_os_getpid silk_uvwasi_os_getpid
#define uv_kill silk_uvwasi_kill
#define uv_guess_handle silk_uvwasi_guess_handle
#define uv_ip4_addr silk_uvwasi_ip4_addr
#define uv_mutex_init silk_uvwasi_mutex_init
#define uv_mutex_destroy silk_uvwasi_mutex_destroy
#define uv_mutex_lock silk_uvwasi_mutex_lock
#define uv_mutex_unlock silk_uvwasi_mutex_unlock
#define uv_rwlock_init silk_uvwasi_rwlock_init
#define uv_rwlock_destroy silk_uvwasi_rwlock_destroy
#define uv_rwlock_wrlock silk_uvwasi_rwlock_wrlock
#define uv_rwlock_wrunlock silk_uvwasi_rwlock_wrunlock
#define uv_loop_init silk_uvwasi_loop_init
#define uv_loop_close silk_uvwasi_loop_close
#define uv_loop_get_data silk_uvwasi_loop_get_data
#define uv_loop_set_data silk_uvwasi_loop_set_data
#define uv_run silk_uvwasi_run
#define uv_stop silk_uvwasi_stop
#define uv_handle_get_data silk_uvwasi_handle_get_data
#define uv_handle_set_data silk_uvwasi_handle_set_data
#define uv_handle_get_loop silk_uvwasi_handle_get_loop
#define uv_unref silk_uvwasi_unref
#define uv_poll_init silk_uvwasi_poll_init
#define uv_poll_stop silk_uvwasi_poll_stop
#define uv_timer_init silk_uvwasi_timer_init
#define uv_tcp_init silk_uvwasi_tcp_init
#define uv_tcp_bind silk_uvwasi_tcp_bind
#define uv_accept silk_uvwasi_accept
#define uv_read_stop silk_uvwasi_read_stop
#define uv_try_write silk_uvwasi_try_write
#define uv_fs_req_cleanup silk_uvwasi_fs_req_cleanup

int uv_translate_sys_error(int sys_errno);
uint64_t uv_hrtime(void);
int uv_gettimeofday(uv_timeval64_t* tv);
int uv_os_getpid(void);
int uv_kill(int pid, int signum);
uv_handle_type uv_guess_handle(uv_file file);
int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr);

int uv_mutex_init(uv_mutex_t* mutex);
void uv_mutex_destroy(uv_mutex_t* mutex);
void uv_mutex_lock(uv_mutex_t* mutex);
void uv_mutex_unlock(uv_mutex_t* mutex);
int uv_rwlock_init(uv_rwlock_t* rwlock);
void uv_rwlock_destroy(uv_rwlock_t* rwlock);
void uv_rwlock_wrlock(uv_rwlock_t* rwlock);
void uv_rwlock_wrunlock(uv_rwlock_t* rwlock);

int uv_loop_init(uv_loop_t* loop);
int uv_loop_close(uv_loop_t* loop);
void* uv_loop_get_data(const uv_loop_t* loop);
void uv_loop_set_data(uv_loop_t* loop, void* data);
int uv_run(uv_loop_t* loop, uv_run_mode mode);
void uv_stop(uv_loop_t* loop);

void* uv_handle_get_data(const uv_handle_t* handle);
void uv_handle_set_data(uv_handle_t* handle, void* data);
uv_loop_t* uv_handle_get_loop(const uv_handle_t* handle);
void uv_unref(uv_handle_t* handle);

int uv_poll_init(uv_loop_t* loop, uv_poll_t* handle, int fd);
int uv_poll_stop(uv_poll_t* handle);
int uv_timer_init(uv_loop_t* loop, uv_timer_t* handle);
int uv_tcp_init(uv_loop_t* loop, uv_tcp_t* handle);
int uv_tcp_bind(uv_tcp_t* handle, const struct sockaddr* addr, unsigned int flags);
int uv_accept(uv_stream_t* server, uv_stream_t* client);
int uv_read_stop(uv_stream_t* stream);
int uv_try_write(uv_stream_t* stream, const uv_buf_t bufs[], unsigned int nbufs);

void uv_fs_req_cleanup(uv_fs_t* req);

/* The functions that take a callback. The Silk function does the work and the wrapper stores
 * the callback in the handle, where the loop finds it. A callback is stored only once the
 * operation has succeeded, which is when libuv stores it. */

int silk_uvwasi_close(uv_handle_t* handle);
int silk_uvwasi_poll_start(uv_poll_t* handle, int events);
int silk_uvwasi_timer_start(uv_timer_t* handle, uint64_t timeout, uint64_t repeat);
int silk_uvwasi_listen(uv_stream_t* stream, int backlog);
int silk_uvwasi_read_start(uv_stream_t* stream);
int silk_uvwasi_shutdown(uv_shutdown_t* req, uv_stream_t* stream);

static inline void uv_close(uv_handle_t* handle, uv_close_cb close_cb) {
  if (handle == NULL)
    return;
  handle->close_cb = close_cb;
  silk_uvwasi_close(handle);
}

static inline int uv_poll_start(uv_poll_t* handle, int events, uv_poll_cb cb) {
  int r = silk_uvwasi_poll_start(handle, events);
  if (r == 0 && events != 0)
    handle->poll_cb = cb;
  return r;
}

static inline int uv_timer_start(uv_timer_t* handle,
                                 uv_timer_cb cb,
                                 uint64_t timeout,
                                 uint64_t repeat) {
  int r;
  if (cb == NULL)
    return UV_EINVAL;
  r = silk_uvwasi_timer_start(handle, timeout, repeat);
  if (r == 0)
    handle->timer_cb = cb;
  return r;
}

static inline int uv_listen(uv_stream_t* stream, int backlog, uv_connection_cb cb) {
  int r = silk_uvwasi_listen(stream, backlog);
  if (r == 0)
    stream->connection_cb = cb;
  return r;
}

static inline int uv_read_start(uv_stream_t* stream, uv_alloc_cb alloc_cb, uv_read_cb read_cb) {
  int r;
  if (stream == NULL || alloc_cb == NULL || read_cb == NULL)
    return UV_EINVAL;
  r = silk_uvwasi_read_start(stream);
  if (r == 0) {
    stream->alloc_cb = alloc_cb;
    stream->read_cb = read_cb;
  }
  return r;
}

static inline int uv_shutdown(uv_shutdown_t* req, uv_stream_t* stream, uv_shutdown_cb cb) {
  int r = silk_uvwasi_shutdown(req, stream);
  if (r == 0)
    req->cb = cb;
  return r;
}

static inline uv_buf_t uv_buf_init(char* base, unsigned int len) {
  uv_buf_t buf;
  buf.base = base;
  buf.len = len;
  return buf;
}

/* The file system requests. uvwasi makes every one synchronously: with a NULL loop and a NULL
 * callback. The wrappers drop those two arguments, so a call that passed anything else would
 * still run synchronously. Each returns what it stores in req->result. */

int silk_uvwasi_fs_close(uv_fs_t* req, uv_file file);
int silk_uvwasi_fs_open(uv_fs_t* req, const char* path, int flags, int mode);
int silk_uvwasi_fs_read(uv_fs_t* req, uv_file file, const uv_buf_t bufs[], unsigned int nbufs, int64_t offset);
int silk_uvwasi_fs_write(uv_fs_t* req, uv_file file, const uv_buf_t bufs[], unsigned int nbufs, int64_t offset);
int silk_uvwasi_fs_stat(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_lstat(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_fstat(uv_fs_t* req, uv_file file);
int silk_uvwasi_fs_fsync(uv_fs_t* req, uv_file file);
int silk_uvwasi_fs_fdatasync(uv_fs_t* req, uv_file file);
int silk_uvwasi_fs_ftruncate(uv_fs_t* req, uv_file file, int64_t offset);
int silk_uvwasi_fs_futime(uv_fs_t* req, uv_file file, double atime, double mtime);
int silk_uvwasi_fs_lutime(uv_fs_t* req, const char* path, double atime, double mtime);
int silk_uvwasi_fs_mkdir(uv_fs_t* req, const char* path, int mode);
int silk_uvwasi_fs_rmdir(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_unlink(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_rename(uv_fs_t* req, const char* path, const char* new_path);
int silk_uvwasi_fs_link(uv_fs_t* req, const char* path, const char* new_path);
int silk_uvwasi_fs_symlink(uv_fs_t* req, const char* path, const char* new_path, int flags);
int silk_uvwasi_fs_readlink(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_realpath(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_opendir(uv_fs_t* req, const char* path);
int silk_uvwasi_fs_readdir(uv_fs_t* req, uv_dir_t* dir);
int silk_uvwasi_fs_closedir(uv_fs_t* req, uv_dir_t* dir);
int silk_uvwasi_random(void* buf, size_t buflen, unsigned int flags);

#define uv_fs_close(loop, req, file, cb) silk_uvwasi_fs_close((req), (file))
#define uv_fs_open(loop, req, path, flags, mode, cb) silk_uvwasi_fs_open((req), (path), (flags), (mode))
#define uv_fs_read(loop, req, file, bufs, nbufs, offset, cb) silk_uvwasi_fs_read((req), (file), (bufs), (nbufs), (offset))
#define uv_fs_write(loop, req, file, bufs, nbufs, offset, cb) silk_uvwasi_fs_write((req), (file), (bufs), (nbufs), (offset))
#define uv_fs_stat(loop, req, path, cb) silk_uvwasi_fs_stat((req), (path))
#define uv_fs_lstat(loop, req, path, cb) silk_uvwasi_fs_lstat((req), (path))
#define uv_fs_fstat(loop, req, file, cb) silk_uvwasi_fs_fstat((req), (file))
#define uv_fs_fsync(loop, req, file, cb) silk_uvwasi_fs_fsync((req), (file))
#define uv_fs_fdatasync(loop, req, file, cb) silk_uvwasi_fs_fdatasync((req), (file))
#define uv_fs_ftruncate(loop, req, file, offset, cb) silk_uvwasi_fs_ftruncate((req), (file), (offset))
#define uv_fs_futime(loop, req, file, atime, mtime, cb) silk_uvwasi_fs_futime((req), (file), (atime), (mtime))
#define uv_fs_lutime(loop, req, path, atime, mtime, cb) silk_uvwasi_fs_lutime((req), (path), (atime), (mtime))
#define uv_fs_mkdir(loop, req, path, mode, cb) silk_uvwasi_fs_mkdir((req), (path), (mode))
#define uv_fs_rmdir(loop, req, path, cb) silk_uvwasi_fs_rmdir((req), (path))
#define uv_fs_unlink(loop, req, path, cb) silk_uvwasi_fs_unlink((req), (path))
#define uv_fs_rename(loop, req, path, new_path, cb) silk_uvwasi_fs_rename((req), (path), (new_path))
#define uv_fs_link(loop, req, path, new_path, cb) silk_uvwasi_fs_link((req), (path), (new_path))
#define uv_fs_symlink(loop, req, path, new_path, flags, cb) silk_uvwasi_fs_symlink((req), (path), (new_path), (flags))
#define uv_fs_readlink(loop, req, path, cb) silk_uvwasi_fs_readlink((req), (path))
#define uv_fs_realpath(loop, req, path, cb) silk_uvwasi_fs_realpath((req), (path))
#define uv_fs_opendir(loop, req, path, cb) silk_uvwasi_fs_opendir((req), (path))
#define uv_fs_readdir(loop, req, dir, cb) silk_uvwasi_fs_readdir((req), (dir))
#define uv_fs_closedir(loop, req, dir, cb) silk_uvwasi_fs_closedir((req), (dir))
#define uv_random(loop, req, buf, buflen, flags, cb) silk_uvwasi_random((buf), (buflen), (flags))

/* The layouts that uvwasi_host.silk assumes. */

_Static_assert(sizeof(void*) == 8 && sizeof(long) == 8 && sizeof(size_t) == 8, "an LP64 target");
_Static_assert(sizeof(uv_buf_t) == 16 && offsetof(uv_buf_t, len) == 8, "uv_buf_t");
_Static_assert(sizeof(uv_timeval64_t) == 16 && offsetof(uv_timeval64_t, tv_usec) == 8, "uv_timeval64_t");
_Static_assert(sizeof(uv_stat_t) == 160 && offsetof(uv_stat_t, st_atim) == 96, "uv_stat_t");
_Static_assert(sizeof(uv_loop_t) == 48 && offsetof(uv_loop_t, time) == 24 && offsetof(uv_loop_t, stop_flag) == 40, "uv_loop_t");
_Static_assert(sizeof(uv_handle_t) == 56 && offsetof(uv_handle_t, close_cb) == 24 && offsetof(uv_handle_t, next_closing) == 48, "uv_handle_t");
_Static_assert(sizeof(uv_poll_t) == 72 && offsetof(uv_poll_t, poll_cb) == 56 && offsetof(uv_poll_t, events) == 68, "uv_poll_t");
_Static_assert(sizeof(uv_timer_t) == 80 && offsetof(uv_timer_t, timeout) == 64, "uv_timer_t");
_Static_assert(sizeof(uv_stream_t) == 104 && offsetof(uv_stream_t, shutdown_req) == 80 && offsetof(uv_stream_t, delayed_error) == 96, "uv_stream_t");
_Static_assert(sizeof(uv_shutdown_t) == 24 && offsetof(uv_shutdown_t, cb) == 16, "uv_shutdown_t");
_Static_assert(sizeof(uv_fs_t) == 184 && offsetof(uv_fs_t, fs_type) == 16 && offsetof(uv_fs_t, statbuf) == 24, "uv_fs_t");
_Static_assert(sizeof(uv_dirent_t) == 16 && offsetof(uv_dirent_t, type) == 8, "uv_dirent_t");
_Static_assert(sizeof(uv_dir_t) == 24 && offsetof(uv_dir_t, dir) == 16, "uv_dir_t");
_Static_assert(sizeof(struct sockaddr_in) == 16, "struct sockaddr_in");

#ifdef __cplusplus
}
#endif

#endif /* SILK_UVWASI_UV_H_ */
