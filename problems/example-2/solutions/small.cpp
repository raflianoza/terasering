#include <bits/stdc++.h>
#define ll long long

using namespace std;

int main(){

    int n;cin>>n;
    vector<ll> a(n);
    for(auto &aa : a) cin>>aa;

    ll mx = LLONG_MIN;
    for(int i = 0; i < n; i++){
        for(int j = 0; j < i; j++){
            mx = max(mx, abs(a[i] - a[j]));
        }
    }

    cout << mx << "\n";

    return 0;
}