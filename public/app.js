const API = '/api';
let token = '';
let currentUser = null;

const el = (id) => document.getElementById(id);
const authMsg = el('authMsg');
const hallsWrap = el('halls');
const myReservationsWrap = el('myReservations');
const ownerWrap = el('ownerReservations');

async function api(path, method = 'GET', body) {
  const res = await fetch(API + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: body ? JSON.stringify(body) : undefined
  });
  return res.json();
}

el('registerForm').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const data = Object.fromEntries(fd.entries());
  const out = await api('/register', 'POST', data);
  authMsg.textContent = out.success ? 'რეგისტრაცია წარმატებულია ✅' : (out.error || 'შეცდომა');
};

el('loginForm').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const out = await api('/login', 'POST', Object.fromEntries(fd.entries()));
  if (!out.token) return authMsg.textContent = out.error || 'შესვლა ვერ მოხერხდა';
  token = out.token;
  currentUser = out.user;
  authMsg.textContent = `მოგესალმები, ${currentUser.name}`;
  el('authSection').classList.add('hidden');
  if (currentUser.role === 'user') {
    el('userPanel').classList.remove('hidden');
    loadHalls();
    loadMyReservations();
  } else {
    el('ownerPanel').classList.remove('hidden');
    loadOwnerReservations();
  }
};

async function loadHalls(lat, lon) {
  const query = lat && lon ? `?lat=${lat}&lon=${lon}` : '';
  const out = await api('/halls' + query);
  hallsWrap.innerHTML = (out.halls || []).map((h) => `
    <div class="hall">
      <h3>${h.name}</h3>
      <p class="muted">${h.address}</p>
      <p>${h.description || ''}</p>
      <p>მაგიდები: ${h.table_count} | ფასი/საათი: ${h.price_per_hour}₾ ${h.distance_km ? `| დაშორება: ${h.distance_km}კმ` : ''}</p>
      <form onsubmit="reserve(event, ${h.id}, ${h.table_count})">
        <input type="number" min="1" max="${h.table_count}" name="table_number" placeholder="მაგიდის ნომერი" required />
        <input type="datetime-local" name="start_time" required />
        <input type="number" min="1" max="8" name="hours" placeholder="საათები" required />
        <button>დაჯავშნა</button>
      </form>
    </div>
  `).join('');
}

window.reserve = async (event, hallId) => {
  event.preventDefault();
  const fd = new FormData(event.target);
  const payload = Object.fromEntries(fd.entries());
  payload.hall_id = hallId;
  payload.table_number = Number(payload.table_number);
  payload.hours = Number(payload.hours);
  payload.start_time = new Date(payload.start_time).toISOString();
  const out = await api('/reserve', 'POST', payload);
  if (!out.reservation_id) return alert(out.error || 'ჯავშნა ვერ შესრულდა');
  const card = prompt(`ჯავშანი შექმნილია. საფასური: ${out.total_price}₾\nშეიყვანე ბარათის ნომერი გადასახდელად:`);
  if (card) {
    const paid = await api('/pay', 'POST', { reservation_id: out.reservation_id, card_number: card });
    alert(paid.success ? `გადახდა წარმატებულია ✅ ****${paid.card_last4}` : (paid.error || 'გადახდა ვერ შესრულდა'));
  }
  loadMyReservations();
};

async function loadMyReservations() {
  const out = await api('/my-reservations');
  myReservationsWrap.innerHTML = (out.reservations || []).map((r) => `
    <div class="res">
      <strong>${r.hall_name}</strong> | მაგიდა #${r.table_number}<br/>
      ${new Date(r.start_time).toLocaleString()} - ${new Date(r.end_time).toLocaleString()}<br/>
      ${r.total_price}₾ | სტატუსი: ${r.payment_status}
    </div>
  `).join('') || '<p class="muted">ჯერ ჯავშანი არ გაქვს.</p>';
}

async function loadOwnerReservations() {
  const out = await api('/owner/reservations');
  ownerWrap.innerHTML = (out.reservations || []).map((r) => `
    <div class="res">
      <strong>${r.hall_name}</strong> | მაგიდა #${r.table_number}<br/>
      კლიენტი: ${r.customer_name} (${r.customer_email})<br/>
      ${new Date(r.start_time).toLocaleString()} - ${new Date(r.end_time).toLocaleString()}<br/>
      ${r.total_price}₾ | ${r.payment_status}
    </div>
  `).join('') || '<p class="muted">ჯავშნები არ არის.</p>';
}

el('locBtn').onclick = () => {
  if (!navigator.geolocation) return alert('Geolocation არ არის მხარდაჭერილი');
  navigator.geolocation.getCurrentPosition(
    (pos) => loadHalls(pos.coords.latitude, pos.coords.longitude),
    () => alert('ლოკაციის წაკითხვა ვერ მოხერხდა')
  );
};

el('refreshReservations').onclick = loadMyReservations;
el('refreshOwner').onclick = loadOwnerReservations;
