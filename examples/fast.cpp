#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; long long k;
    scanf("%d %lld", &n, &k);
    unordered_map<long long,int> seen;
    seen.reserve(1<<17);
    long long total = 0;
    for (int i = 0; i < n; i++) {
        long long x; scanf("%lld", &x);
        auto it = seen.find(k - x);
        if (it != seen.end()) total += it->second;
        seen[x]++;
    }
    printf("%lld\n", total);
}
