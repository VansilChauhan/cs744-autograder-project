#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

int main(int argc, char *argv[])
{
    if (argc < 4)
    {
        printf("invalid arg");
        exit(1);
    }
    int num = atoi(argv[1]);
    if (num % 2 == 0)
    {
        printf("%d", num * num);
    }
    else
    {
        printf("%d", num);
    }
    return 0;
}
