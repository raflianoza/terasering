#include <bits/stdc++.h>
using namespace std;
int main() {
    int n;
    scanf("%d", &n);
    long long lo = LLONG_MAX, hi = LLONG_MIN;
    for (int i = 0; i < n; i++) {
        long long x;
        scanf("%lld", &x);
        lo = min(lo, x);
        hi = max(hi, x);
    }
    printf("%lld\n", hi - lo);
}
