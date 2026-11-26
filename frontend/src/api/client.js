// HTTP client for backend API communication with AppError parsing and network handling

const BASE_URL = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || "";

export const TOKEN_STORAGE_KEY = "apex_auth_token";

export function getStoredToken() {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // Ignore storage errors in private browsing
  }
}

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    "Accept": "application/json",
    ...(options.headers || {}),
  };

  const token = getStoredToken();
  const isPublicAuthEndpoint =
    endpoint.startsWith("/api/v1/auth/login") ||
    endpoint.startsWith("/api/v1/auth/register");

  if (token && !headers["Authorization"] && !isPublicAuthEndpoint) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (networkError) {
    const error = new Error("Unable to connect to server. Check your network connection.");
    error.code = "NETWORK_ERROR";
    error.status = 0;
    error.isNetwork = true;
    throw error;
  }

  if (response.status === 204) {
    return { ok: true, status: 204, data: null };
  }

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await response.text();
      data = { raw: text };
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const errPayload = data && data.error ? data.error : null;
    const detailPayload = data && data.detail ? data.detail : null;

    let code = "REQUEST_FAILED";
    let message = "An error occurred while processing your request.";
    let details = null;

    if (errPayload) {
      code = errPayload.code || code;
      message = errPayload.message || message;
      details = errPayload.details || null;
      if (code === "VALIDATION_ERROR" && Array.isArray(details) && details.length > 0) {
        const formatted = details
          .map((d) => {
            const loc = Array.isArray(d.loc)
              ? d.loc.filter((part) => part !== "body").join(".")
              : "";
            const msg = d.msg ? d.msg.replace(/^Value error,\s*/i, "") : "invalid value";
            return loc ? `${loc}: ${msg}` : msg;
          })
          .join(", ");
        if (formatted) {
          message = formatted;
        }
      }
    } else if (typeof detailPayload === "string") {
      message = detailPayload;
    } else if (Array.isArray(detailPayload) && detailPayload.length > 0) {
      message = detailPayload
        .map((d) => {
          const loc = Array.isArray(d.loc)
            ? d.loc.filter((part) => part !== "body").join(".")
            : "";
          const msg = d.msg ? d.msg.replace(/^Value error,\s*/i, "") : "Invalid field";
          return loc ? `${loc}: ${msg}` : msg;
        })
        .join(", ");
      details = detailPayload;
    }

    const error = new Error(message);
    error.code = code;
    error.status = response.status;
    error.details = details;
    error.data = data;
    throw error;
  }

  return { ok: true, status: response.status, data };
}

export const api = {
  auth: {
    async register(nameOrObj, email, password) {
      let body;
      if (typeof nameOrObj === "object" && nameOrObj !== null) {
        body = nameOrObj;
      } else {
        body = { name: nameOrObj, email, password };
      }
      const res = await request("/api/v1/auth/register", {
        method: "POST",
        body,
      });
      return res.data;
    },
    async login(emailOrObj, password) {
      let body;
      if (typeof emailOrObj === "object" && emailOrObj !== null) {
        body = emailOrObj;
      } else {
        body = { email: emailOrObj, password };
      }
      const res = await request("/api/v1/auth/login", {
        method: "POST",
        body,
      });
      return res.data;
    },
    async me() {
      const res = await request("/api/v1/auth/me", {
        method: "GET",
      });
      return res.data;
    },
    async logout() {
      try {
        await request("/api/v1/auth/logout", {
          method: "POST",
        });
      } finally {
        setStoredToken(null);
      }
    },
  },

  orders: {
    async list() {
      const res = await request("/api/v1/orders", {
        method: "GET",
      });
      return res.data;
    },
    async get(orderId) {
      const res = await request(`/api/v1/orders/${orderId}`, {
        method: "GET",
      });
      return res.data;
    },
  },

  refunds: {
    async request({ order_id, amount, reason, ticket_id = null, idempotencyKey = null }) {
      const headers = {};
      if (idempotencyKey) {
        headers["Idempotency-Key"] = idempotencyKey;
      }
      const res = await request("/api/v1/refunds", {
        method: "POST",
        headers,
        body: {
          order_id,
          amount,
          reason,
          ticket_id,
        },
      });
      return { status: res.status, data: res.data };
    },
    async list() {
      const res = await request("/api/v1/refunds", {
        method: "GET",
      });
      return res.data;
    },
  },

  tickets: {
    async list() {
      const res = await request("/api/v1/tickets", {
        method: "GET",
      });
      return res.data;
    },
    async create({ subject, description, order_id = null, category = "other" }) {
      const res = await request("/api/v1/tickets", {
        method: "POST",
        body: {
          subject,
          description,
          order_id,
          category,
        },
      });
      return res.data;
    },
    async get(ticketId) {
      const res = await request(`/api/v1/tickets/${ticketId}`, {
        method: "GET",
      });
      return res.data;
    },
    async getMessages(ticketId) {
      const res = await request(`/api/v1/tickets/${ticketId}/messages`, {
        method: "GET",
      });
      return res.data;
    },
    async sendMessage(ticketId, { content }) {
      const res = await request(`/api/v1/tickets/${ticketId}/messages`, {
        method: "POST",
        body: { content },
      });
      return res.data;
    },
  },

  meta: {
    async enums() {
      const res = await request("/api/v1/meta/enums", { method: "GET" });
      return res.data;
    },
    async config() {
      const res = await request("/api/v1/meta/config", { method: "GET" });
      return res.data;
    },
  },

  staff: {
    async overview() {
      const res = await request("/api/v1/staff/overview", { method: "GET" });
      return res.data;
    },
    async listTickets(params = {}) {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
          query.set(k, v);
        }
      });
      const qs = query.toString();
      const res = await request(`/api/v1/staff/tickets${qs ? `?${qs}` : ""}`, { method: "GET" });
      return res.data;
    },
    async getTicket(ticketId) {
      const res = await request(`/api/v1/staff/tickets/${ticketId}`, { method: "GET" });
      return res.data;
    },
    async patchTicket(ticketId, payload) {
      const res = await request(`/api/v1/staff/tickets/${ticketId}`, {
        method: "PATCH",
        body: payload,
      });
      return res.data;
    },
    async getMessages(ticketId, after = null) {
      const qs = after ? `?after=${encodeURIComponent(after)}` : "";
      const res = await request(`/api/v1/staff/tickets/${ticketId}/messages${qs}`, { method: "GET" });
      return res.data;
    },
    async postMessage(ticketId, { content }) {
      const res = await request(`/api/v1/staff/tickets/${ticketId}/messages`, {
        method: "POST",
        body: { content },
      });
      return res.data;
    },
    async getNotes(ticketId) {
      const res = await request(`/api/v1/staff/tickets/${ticketId}/notes`, { method: "GET" });
      return res.data;
    },
    async postNote(ticketId, { note }) {
      const res = await request(`/api/v1/staff/tickets/${ticketId}/notes`, {
        method: "POST",
        body: { note },
      });
      return res.data;
    },
    async listEscalations(params = {}) {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
          query.set(k, v);
        }
      });
      const qs = query.toString();
      const res = await request(`/api/v1/staff/escalations${qs ? `?${qs}` : ""}`, { method: "GET" });
      return res.data;
    },
    async getEscalation(escalationId) {
      const res = await request(`/api/v1/staff/escalations/${escalationId}`, { method: "GET" });
      return res.data;
    },
    async assignEscalation(escalationId, assigneeId = null) {
      const res = await request(`/api/v1/staff/escalations/${escalationId}/assign`, {
        method: "POST",
        body: { assignee_id: assigneeId },
      });
      return res.data;
    },
    async decideEscalation(escalationId, { decision, note, message_to_customer = null }) {
      const res = await request(`/api/v1/staff/escalations/${escalationId}/decision`, {
        method: "POST",
        body: { decision, note, message_to_customer },
      });
      return res.data;
    },
  },
};
