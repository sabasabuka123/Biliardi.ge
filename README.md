# Biliardi.ge

სრული ვებ-აპლიკაცია საბილიარდოების მოძებნის, მაგიდის დაჯავშნის, გადახდის და მეპატრონის კონტროლის პანელით.

## ფუნქციები
- მომხმარებლის რეგისტრაცია/შესვლა.
- ახლომდებარე საბილიარდოების მოძებნა (Geolocation + distance sorting).
- მაგიდის დაჯავშნა დროის სლოტზე.
- ჯავშნის გადახდა (დემო ბარათის იმიტაციით).
- მომხმარებლის საკუთარი ჯავშნების გვერდი.
- მეპატრონის პანელი ყველა ჯავშნის საკონტროლოდ (მაგიდა/საათი/კლიენტი/სტატუსი).

## გაშვება
```bash
python3 server.py
```
შემდეგ გახსენი: http://localhost:8000

## Demo Owner
- Email: `owner1@biliardi.ge`
- Password: `Owner123!`

## სტექი
- Backend: Python `http.server` + `sqlite3`
- Frontend: HTML/CSS/Vanilla JS
- DB: SQLite (`biliardi.db` ავტომატურად იქმნება)

## Security regression tests

```bash
python3 -m unittest discover -s tests -v
npm ci
npm test
```

Backend tests use an isolated temporary SQLite database and HTTP server. They cover
registration → login → halls → reservation → demo payment → customer/owner lists,
RFC3339 UTC/offset input, invalid input, overlap/adjacent slots, legacy offset records,
and raw/encoded traversal plus symlink escapes. Timestamps require a timezone and
support fractional seconds up to six digits; new reservations are stored in UTC.
The DOM test checks hostile values in every owner dashboard field and the empty state.

Optional real Chromium check (requires Playwright and its browser download):
```bash
npm install --no-save playwright
npx playwright install chromium
npm run test:browser
```
