#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#define BUFF_SIZE 1024

static double now_ms(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

#define RUN_CPU_SEC 2                       /* CPU seconds */
#define RUN_AS_BYTES (256UL * 1024 * 1024)  /* address space */
#define RUN_NPROC 64                        /* processes, anti fork-bomb */
#define RUN_FSIZE_BYTES (8UL * 1024 * 1024) /* max file written */
#define RUN_NOFILE 64                       /* open file descriptors */
#define RUN_TIMEOUT_MS 3000                 /* wall clock */

#define COMPILE_CPU_SEC 10
#define COMPILE_AS_BYTES (1024UL * 1024 * 1024)
#define COMPILE_FSIZE_BYTES (64UL * 1024 * 1024)
#define COMPILE_TIMEOUT_MS 15000

#define MAX_UPLOAD_BYTES (1UL * 1024 * 1024)

#define KILLED_MARKER "<<killed>>"

static int sandbox_enabled = 1;

static void init_sandbox_flag(void) {
  const char *e = getenv("SANDBOX");
  sandbox_enabled = !(e && (e[0] == '0'));
  fprintf(stderr, "SANDBOX %s\n", sandbox_enabled ? "enabled" : "DISABLED");
}

static void set_limit(int resource, rlim_t value) {
  struct rlimit rl;
  rl.rlim_cur = value;
  rl.rlim_max = value;
  setrlimit(resource, &rl);
}

static int wait_deadline_pidfd(pid_t pid, int timeout_ms) {
#ifdef SYS_pidfd_open
  int pfd = (int)syscall(SYS_pidfd_open, pid, 0);
  if (pfd < 0)
    return -1;
  double start = now_ms();
  while (1) {
    int remaining = timeout_ms - (int)(now_ms() - start);
    if (remaining <= 0) {
      close(pfd);
      return 1;
    }
    struct pollfd p;
    p.fd = pfd;
    p.events = POLLIN;
    int r = poll(&p, 1, remaining);
    if (r > 0) {
      close(pfd);
      return 0;
    }
    if (r == 0) {
      close(pfd);
      return 1;
    }
    if (errno != EINTR) {
      close(pfd);
      return -1;
    }
  }
#else
  (void)pid;
  (void)timeout_ms;
  return -1;
#endif
}

static void apply_child_limits(int cpu_sec, rlim_t as_bytes, rlim_t fsize,
                               int nproc, int nofile) {
  if (!sandbox_enabled)
    return;

  setsid();

  set_limit(RLIMIT_CPU, cpu_sec);
  set_limit(RLIMIT_AS, as_bytes);
  set_limit(RLIMIT_FSIZE, fsize);
  set_limit(RLIMIT_CORE, 0);
  if (nofile > 0)
    set_limit(RLIMIT_NOFILE, nofile);
  if (nproc > 0)
    set_limit(RLIMIT_NPROC, nproc);
}

static int wait_timeout(pid_t pid, int timeout_ms, int *status) {
  if (!sandbox_enabled) {
    waitpid(pid, status, 0);
    return 0;
  }

  int timed_out = wait_deadline_pidfd(pid, timeout_ms);
  if (timed_out < 0) {
    double start = now_ms();
    timed_out = 0;
    while (1) {
      pid_t r = waitpid(pid, status, WNOHANG);
      if (r == pid)
        return 0;
      if (r < 0 && errno != EINTR)
        return 0;
      if (now_ms() - start >= timeout_ms) {
        timed_out = 1;
        break;
      }
      struct timespec nap = {0, 2 * 1000 * 1000}; /* 2 ms */
      nanosleep(&nap, NULL);
    }
  }

  if (!timed_out) {
    waitpid(pid, status, 0);
    return 0;
  }
  kill(-pid, SIGKILL);
  kill(pid, SIGKILL);
  waitpid(pid, status, 0);
  return 1;
}

static int capture_with_timeout(pid_t pid, int readfd, int timeout_ms,
                                char *out, size_t outcap, int *status) {
  size_t used = 0;
  int timed_out = 0;
  double start = now_ms();

  while (1) {
    int remaining = -1;
    if (timeout_ms >= 0) {
      remaining = timeout_ms - (int)(now_ms() - start);
      if (remaining <= 0) {
        timed_out = 1;
        break;
      }
    }

    struct pollfd pfd;
    pfd.fd = readfd;
    pfd.events = POLLIN;
    int pr = poll(&pfd, 1, remaining);
    if (pr < 0) {
      if (errno == EINTR)
        continue;
      break;
    }
    if (pr == 0) {
      timed_out = 1;
      break;
    }

    char chunk[4096];
    ssize_t n = read(readfd, chunk, sizeof(chunk));
    if (n < 0) {
      if (errno == EINTR)
        continue;
      break;
    }
    if (n == 0)
      break;
    if (used + 1 < outcap) {
      size_t room = outcap - 1 - used;
      size_t take = ((size_t)n < room) ? (size_t)n : room;
      memcpy(out + used, chunk, take);
      used += take;
    }
  }
  out[used] = '\0';

  if (timed_out) {
    kill(-pid, SIGKILL);
    kill(pid, SIGKILL);
  }
  waitpid(pid, status, 0);
  return timed_out;
}

#define RESET "\033[0m"   // Reset to default color
#define GREEN "\033[32m"  // Green text
#define RED "\033[31m"    // Red text
#define YELLOW "\033[33m" // Yellow text

#define MAX_TEST_CASES 100
#define MAX_OUTPUT_LENGTH 100

pthread_mutex_t queue_lock;
pthread_mutex_t client_count_lock;
pthread_cond_t task_available;

char test_case_solution_inputs[MAX_TEST_CASES][MAX_OUTPUT_LENGTH];
char test_case_solution_outputs[MAX_TEST_CASES][MAX_OUTPUT_LENGTH];
int test_case_count = 0;
int client_count = 0;

int get_client_count() {
  pthread_mutex_lock(&client_count_lock);
  int temp = client_count;
  client_count++;
  pthread_mutex_unlock(&client_count_lock);
  return temp;
}

int compare_test_case_output(char *compare_str, int index) {
  if (strcmp(test_case_solution_outputs[index], compare_str) == 0) {
    return 1;
  }
  return 0;
}
typedef struct TaskNode {
  int *socket;
  struct TaskNode *next;
} TaskNode;

typedef struct {
  TaskNode *front;
  TaskNode *rear;
  int size;
} TaskQueue;

TaskQueue queue;

TaskNode *create_task_node(int *socket) {
  TaskNode *new_node = (TaskNode *)malloc(sizeof(TaskNode));
  new_node->socket = socket;
  new_node->next = NULL;
  return new_node;
}

void enqueue_task(int *arg) {
  TaskNode *new_node = create_task_node(arg);
  pthread_mutex_lock(&queue_lock);
  if (queue.rear == NULL) {
    queue.front = queue.rear = new_node;
  } else {
    queue.rear->next = new_node;
    queue.rear = new_node;
  }
  queue.size++;
  pthread_cond_signal(&task_available);
  pthread_mutex_unlock(&queue_lock);
}

int *dequeue_task() {
  pthread_mutex_lock(&queue_lock);
  while (queue.size == 0) {
    pthread_cond_wait(&task_available, &queue_lock);
  }
  TaskNode *temp = queue.front;
  int *socket = temp->socket;
  queue.front = queue.front->next;
  if (queue.front == NULL) {
    queue.rear = NULL;
  }
  free(temp);
  queue.size--;
  pthread_mutex_unlock(&queue_lock);
  return socket;
}

int compile(char *filename, char *executable) {
  char *compiler = "/usr/bin/gcc";
  char *output_file = "-o";
  int pid = fork();
  int status = 0;
  if (pid < 0) {
    perror("Fork Failed");
    exit(1);
  } else if (pid == 0) {
    apply_child_limits(COMPILE_CPU_SEC, COMPILE_AS_BYTES, COMPILE_FSIZE_BYTES,
                       0, 0);
    execlp(compiler, compiler, filename, output_file, executable, (char *)NULL);
    perror("Error executing gcc");
    _exit(127);
  }

  if (wait_timeout(pid, COMPILE_TIMEOUT_MS, &status)) {
    fprintf(stderr, "SANDBOX compile killed after %d ms: %s\n",
            COMPILE_TIMEOUT_MS, filename);
    return -1;
  }
  return (WIFEXITED(status) && WEXITSTATUS(status) == 0) ? 0 : -1;
}

char *run(char *executable, char *input) {
  char *output = (char *)malloc(MAX_OUTPUT_LENGTH * sizeof(char));
  int pipe_fd[2];
  pid_t pid;
  char program[100];

  sprintf(program, "./%s", executable);
  if (pipe(pipe_fd) == -1) {
    perror("pipe");
    exit(1);
  }

  pid = fork();
  if (pid < 0) {
    perror("fork error");
    exit(1);
  } else if (pid == 0) {
    close(pipe_fd[0]);
    dup2(pipe_fd[1], STDOUT_FILENO);
    close(pipe_fd[1]);

    apply_child_limits(RUN_CPU_SEC, RUN_AS_BYTES, RUN_FSIZE_BYTES, RUN_NPROC,
                       RUN_NOFILE);

    char *args[] = {program, input, NULL};
    execv(args[0], args);

    perror("execv fail");
    _exit(127);
  } else {
    close(pipe_fd[1]);
    int status = 0;
    int killed = capture_with_timeout(pid, pipe_fd[0],
                                      sandbox_enabled ? RUN_TIMEOUT_MS : -1,
                                      output, MAX_OUTPUT_LENGTH, &status);
    close(pipe_fd[0]);
    if (killed) {
      fprintf(stderr, "SANDBOX run killed after %d ms: %s\n", RUN_TIMEOUT_MS,
              program);
      strcpy(output, KILLED_MARKER);
    } else if (WIFSIGNALED(status)) {
      fprintf(stderr, "SANDBOX run terminated by signal %d: %s\n",
              WTERMSIG(status), program);
      strcpy(output, KILLED_MARKER);
    }
  }
  return output;
}

void *thread_work(void *arg) {
  while (1) {
    int *new_socket = dequeue_task();
    int socket = *((int *)new_socket);
    free(new_socket);

    int rwbytes;
    char buffer[BUFF_SIZE] = {0};
    char result[MAX_OUTPUT_LENGTH];

    bzero(buffer, BUFF_SIZE);

    int n;
    int client_number = get_client_count();
    FILE *fp;
    time_t t = time(NULL);
    char cfile[100];
    snprintf(cfile, sizeof(cfile), "student_program_%ld_%d.c", t,
             client_number);

    t = time(NULL);
    char executable[100];
    snprintf(executable, sizeof(executable), "student_program_%ld_%d.o", t,
             client_number);

    fp = fopen(cfile, "w");
    if (fp == NULL) {
      printf("Error in file creation\n");
      exit(1);
    }
    unsigned long uploaded = 0;
    int oversize = 0;
    while (1) {
      n = recv(socket, buffer, BUFF_SIZE, 0);
      if (n <= 0) {
        break;
      }
      if (uploaded + (unsigned long)n > MAX_UPLOAD_BYTES) {
        oversize = 1;
        break;
      }
      fwrite(buffer, 1, (size_t)n, fp);
      uploaded += (unsigned long)n;
      bzero(buffer, BUFF_SIZE);
    }
    fclose(fp);

    if (oversize) {
      const char *msg = RED "submission rejected: exceeds "
                            "1 MB source limit" RESET;
      fprintf(stderr, "SANDBOX upload rejected client=%d (> %lu bytes)\n",
              client_number, MAX_UPLOAD_BYTES);
      write(socket, msg, strlen(msg));
      remove(cfile);
      close(socket);
      continue;
    }
    char command[128];

    double compile_start = now_ms();
    compile(cfile, executable);
    double compile_end = now_ms();
    int success_count = 0;
    char *client_results[MAX_TEST_CASES];
    for (int i = 0; i < test_case_count; i++) {
      client_results[i] = run(executable, test_case_solution_inputs[i]);
      if (compare_test_case_output(client_results[i], i)) {
        success_count++;
      }
    }
    double exec_end = now_ms();
    fprintf(stderr,
            "TIMING client=%d compile_ms=%.3f exec_ms=%.3f total_ms=%.3f "
            "test_cases=%d\n",
            client_number, compile_end - compile_start, exec_end - compile_end,
            exec_end - compile_start, test_case_count);
    sprintf(result,
            YELLOW " %.2f %%"
                   ", " RED "(" GREEN "%d" RED "/%d)" RESET
                   " test cases passed!",
            (success_count / (float)test_case_count) * 100, success_count,
            test_case_count);
    rwbytes = write(socket, result, strlen(result));
    if (rwbytes < 0) {
      perror("Write Error");
      close(socket);
      pthread_exit(NULL);
    }
    remove(cfile);
    remove(executable);
    close(socket);
  }
}

void handle_task(int new_socket) {
  int *client_sock = malloc(sizeof(int));
  if (client_sock == NULL) {
    printf("Memory allocation fail\n");
    close(new_socket);
    return;
  }
  *client_sock = new_socket;
  enqueue_task(client_sock);
}

void reset_queue() {
  pthread_mutex_init(&queue_lock, NULL);
  queue.front = NULL;
  queue.rear = NULL;
  queue.size = 0;
}

int main(int argc, char *argv[]) {
  if (argc < 5) {
    printf("usage: ./filename <port> <thread_count> <solution.c> "
           "<test_cases.txt>\n");
    exit(1);
  }

  init_sandbox_flag();

  int port = atoi(argv[1]);
  int thread_count = atoi(argv[2]);
  char *solution_file = argv[3];
  char *test_cases_file = argv[4];
  char *executable = "solution.o";
  compile(solution_file, executable);

  FILE *input_test_cases_file = fopen(test_cases_file, "r");
  if (input_test_cases_file == NULL) {
    printf("Error in testcase file reading");
    exit(1);
  }
  while (test_case_count < MAX_TEST_CASES &&
         fgets(test_case_solution_inputs[test_case_count], MAX_OUTPUT_LENGTH,
               input_test_cases_file)) {
    test_case_solution_inputs[test_case_count][strcspn(
        test_case_solution_inputs[test_case_count], "\n")] = '\0';
    char *temp_result =
        run(executable, test_case_solution_inputs[test_case_count]);
    strcpy(test_case_solution_outputs[test_case_count], temp_result);
    free(temp_result);
    test_case_count++;
  }

  pthread_mutex_init(&queue_lock, NULL);
  pthread_mutex_init(&client_count_lock, NULL);
  pthread_cond_init(&task_available, NULL);

  int main_socket, new_socket;
  struct sockaddr_in server_addr, client_addr;
  socklen_t client_len = sizeof(client_addr);

  reset_queue();

  if ((main_socket = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
    printf("Socket creation error\n");
    exit(1);
  }

  server_addr.sin_family = AF_INET;
  server_addr.sin_addr.s_addr = INADDR_ANY;
  server_addr.sin_port = htons(port);

  if (bind(main_socket, (struct sockaddr *)&server_addr, sizeof(server_addr)) <
      0) {
    perror("Binding Failed.");
    exit(1);
  }

  if (listen(main_socket, 10) < 0) {
    perror("Listening Failed.");
    exit(1);
  }

  pthread_t threads[thread_count];
  for (int i = 0; i < thread_count; i++) {
    pthread_create(&threads[i], NULL, &thread_work, NULL);
  }

  printf("server is ready to accept connections... on port %d\n", port);

  while (1) {
    if ((new_socket = accept(main_socket, (struct sockaddr *)&client_addr,
                             &client_len)) < 0) {
      printf("Accept failed.");
      continue;
    }
    handle_task(new_socket);
  }
  close(main_socket);
  pthread_mutex_destroy(&queue_lock);
  pthread_mutex_destroy(&client_count_lock);
  pthread_cond_destroy(&task_available);
  return 0;
}
