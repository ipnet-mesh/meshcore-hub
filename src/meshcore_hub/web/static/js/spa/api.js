/**
 * MeshCore Hub SPA - API Client
 *
 * Wrapper around fetch() for making API calls to the proxied backend.
 */

/**
 * Make a GET request and return parsed JSON.
 * @param {string} path - URL path (e.g., '/api/v1/nodes')
 * @param {Object} [params] - Query parameters
 * @returns {Promise<any>} Parsed JSON response
 */
export async function apiGet(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== '') {
            url.searchParams.set(k, String(v));
        }
    }
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
}

/**
 * Make a POST request with JSON body.
 * @param {string} path - URL path
 * @param {Object} body - Request body
 * @returns {Promise<any>} Parsed JSON response
 */
export async function apiPost(path, body) {
    const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error: ${response.status} - ${text}`);
    }
    if (response.status === 204) return null;
    return response.json();
}

/**
 * Make a PUT request with JSON body.
 * @param {string} path - URL path
 * @param {Object} body - Request body
 * @returns {Promise<any>} Parsed JSON response
 */
export async function apiPut(path, body) {
    const response = await fetch(path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error: ${response.status} - ${text}`);
    }
    if (response.status === 204) return null;
    return response.json();
}

/**
 * Make a DELETE request.
 * @param {string} path - URL path
 * @returns {Promise<void>}
 */
export async function apiDelete(path) {
    const response = await fetch(path, { method: 'DELETE' });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error: ${response.status} - ${text}`);
    }
}

/**
 * Make a POST request with form-encoded body.
 * @param {string} path - URL path
 * @param {Object} data - Form data as key-value pairs
 * @returns {Promise<any>} Parsed JSON response
 */
export async function apiPostForm(path, data) {
    const body = new URLSearchParams(data);
    const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error: ${response.status} - ${text}`);
    }
    if (response.status === 204) return null;
    return response.json();
}
