#include <bits/stdc++.h>
using namespace std;
int main() {
    int n;
    scanf("%d", &n);
    long long lo = 0, hi = 0;
    for (int i = 0; i < n; i++) {
        long long x;
        scanf("%lld", &x);
        lo = min(lo, x);
        hi = max(hi, x);
    }
    printf("%lld\n", hi - lo);
}
