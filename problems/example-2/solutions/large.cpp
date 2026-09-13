#include <bits/stdc++.h>
#define ll long long

using namespace std;

int main(){

    int n;cin>>n;
    vector<ll> a(n);
    for(auto &aa : a) cin>>aa;

    sort(a.begin(), a.end());

    cout << a.back() - a[0] << "\n";

    return 0;
}