#include <bits/stdc++.h>
using namespace std;

int main() {
    int n;
    cin >> n;

    vector<int> a(n);
    for (int i = 0; i < n; i++) {
        cin >> a[i];
    }

    int m;
    cin >> m;

    while (m--) {
        int q;
        cin >> q;

        int sum = 0;

        for (int i = 0; i < n; i++) {
            sum += a[i];

            if (q <= sum) {
                cout << i + 1 << '\n';
                break;
            }
        }
    }

    return 0;
}