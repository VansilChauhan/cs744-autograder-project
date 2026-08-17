# cs744-project-auto-grader

A multithreaded C auto-grader. A TCP server compiles and runs student-submitted C programs against a reference solution's test cases; a TCP client sends a student's `.c` file to be graded and prints the pass percentage.

## Build

```
make          # compiles server.c -> server.o and client.c -> client.o
make clean    # removes server.o/client.o and leftover student_program_*.c/.o files
```

## Run

Start the server (compiles `solution.c`, precomputes expected outputs from `test_cases.txt`, listens for submissions):

```
./runserver.sh
# equivalent to:
./server.o <port> <thread_count> <solution.c> <test_cases.txt>
```

Submit a student program for grading:

```
./client.o <server_ip> <server_port> <student_file.c>
```

Simulate `N` concurrent client submissions (cycling through `program_1.c`..`program_4.c`):

```
./runclient.sh <N>
```
# cs744-autograder-project
