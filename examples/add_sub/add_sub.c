#include <stdio.h>

/* اقتران فرعي لعملية الجمع */
int Add(int a, int b)
{
    return a + b;
}

/* اقتران فرعي لعملية الطرح */
int Sub(int a, int b)
{
    return a - b;
}

int main()
{
    int num1, num2;
    int sum, diff;

    printf("ادخل الرقم الاول: ");
    scanf("%d", &num1);

    printf("ادخل الرقم الثاني: ");
    scanf("%d", &num2);

    sum = Add(num1, num2);
    diff = Sub(num1, num2);

    printf("ناتج الجمع = %d\n", sum);
    printf("ناتج الطرح = %d\n", diff);

    return 0;
}
