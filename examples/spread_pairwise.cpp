#include <bits/stdc++.h>
using namespace std;
int main() {
    int n;
    scanf("%d", &n);
    vector<long long> a(n);
    for (auto &x : a) scanf("%lld", &x);
    long long best = 0;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
            best = max(best, llabs(a[i] - a[j]));
    printf("%lld\n", best);
}
