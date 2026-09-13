#include <bits/stdc++.h>
#define ll long long
#define pii pair<int, int>
#define pli pair<ll, int>
#define pll pair<ll, ll>
#define pb push_back
#define fi first
#define se second
#define cont continue
#define rafligoldmedalosn ios::sync_with_stdio(0);cin.tie(0);

using namespace std;

int main(){

    rafligoldmedalosn

    int n;cin>>n;
    vector<ll> a(n + 1);
    for(int i = 1; i <= n; i++) cin>>a[i];

    vector<ll> pref(n + 1, 0);
    for(int i = 1; i <= n; i++) pref[i] = pref[i - 1] + a[i];

    int q;cin>>q;
    while(q--){
        ll x;cin>>x;

        auto it = lower_bound(pref.begin(), pref.end(), x) - pref.begin();
        cout << (int)it << "\n";
    }
    
    return 0;
}