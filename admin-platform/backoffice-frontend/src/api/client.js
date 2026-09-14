// 같은 origin 의 /api 로 요청 → nginx(운영) 또는 vite proxy(개발)가 backoffice-backend:8000 으로 전달
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }
  return response.json();
}

export const api = {
  getDashboard: () => request('/api/admin/dashboard'),
  getUsers: () => request('/api/admin/users'),
  updateUserStatus: (id, status) =>
    request(`/api/admin/users/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  sendNotice: (message) =>
    request('/api/admin/notices', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
};
