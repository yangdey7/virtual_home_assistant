export class ApiError extends Error {
  constructor(message, data = {}) {
    super(message);
    this.name = 'ApiError';
    this.data = data;
  }
}

export async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new ApiError(data.message || 'The command could not be completed.', data);
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error.name === 'AbortError') {
      throw new ApiError('The server took too long to respond. Check the current room state before repeating the command.');
    }
    throw new ApiError('Cannot reach the bedroom server. Check that it is running, then try again.');
  } finally {
    clearTimeout(timeout);
  }
}

export const post = (path, payload) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
});

