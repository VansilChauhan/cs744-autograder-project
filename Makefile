all: server.c client.c
	gcc server.c -o server.o -lpthread
	gcc client.c -o client.o -lpthread

clean:
	rm -f student_program_*.c student_program_*.o
	rm -f *.o