#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc, char *argv[])
{
    if (argc < 2)
    {
        printf("invalid arg");
        exit(1);
    }
    int num = atoi(argv[1]);

    printf("%d", num * num);
    return 0;
}
