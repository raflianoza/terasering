#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; long long k;
    scanf("%d %lld", &n, &k);
    vector<long long> a(n);
    for (auto &x : a) scanf("%lld", &x);
    long long total = 0;
    for (int i = 0; i < n; i++)
        for (int j = i+1; j < n; j++)
            if (a[i] + a[j] == k) total++;
    printf("%lld\n", total);
}
