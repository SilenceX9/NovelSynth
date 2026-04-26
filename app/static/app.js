function setStatus(id, msg, type) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.className = 'status' + (type ? ' ' + type : '');
}

function showSection(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'block';
}

function getBookId() {
  return localStorage.getItem('book_id');
}

function setBookId(id) {
  localStorage.setItem('book_id', id);
}
