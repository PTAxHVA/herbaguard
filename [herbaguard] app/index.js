document.addEventListener("DOMContentLoaded", function () {
    const api = window.HerbaGuardAPI;
    if (!api) {
        return;
    }

    const dashboardAlerts = document.getElementById("dashboardAlerts");
    const upcomingReminderList = document.getElementById("upcomingReminderList");
    const recentCheckList = document.getElementById("recentCheckList");
    const dashboardError = document.getElementById("dashboardError");
    const btnRefreshDashboard = document.getElementById("btnRefreshDashboard");

    const heroCheckAction = document.getElementById("heroCheckAction");
    const btnQuickCheck = document.getElementById("btnQuickCheck");

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function showError(message) {
        if (!dashboardError) {
            return;
        }

        if (!message) {
            dashboardError.textContent = "";
            dashboardError.classList.add("hidden");
            return;
        }

        dashboardError.textContent = message;
        dashboardError.classList.remove("hidden");
    }

    function emptyCard(text) {
        return `<div class="empty-state">${escapeHtml(text)}</div>`;
    }

    function formatDateTime(isoText) {
        try {
            const date = new Date(isoText);
            if (Number.isNaN(date.getTime())) {
                return "Không rõ";
            }
            return date.toLocaleString("vi-VN", {
                hour: "2-digit",
                minute: "2-digit",
                day: "2-digit",
                month: "2-digit",
            });
        } catch (error) {
            return "Không rõ";
        }
    }

    function toSummaryLabel(level) {
        if (level === "danger") {
            return "Nguy cơ cao";
        }
        if (level === "warning") {
            return "Cần theo dõi";
        }
        return "An toàn";
    }

    function renderAlerts(alerts) {
        if (!dashboardAlerts) {
            return;
        }

        if (!alerts || alerts.length === 0) {
            dashboardAlerts.innerHTML = emptyCard("Chưa có cảnh báo mới.");
            return;
        }

        dashboardAlerts.innerHTML = alerts
            .map((item) => {
                const typeClass = item.type === "interaction" ? "warning" : item.type === "low_stock" ? "danger-soft" : "info";
                const icon = item.type === "interaction"
                    ? "fa-triangle-exclamation"
                    : item.type === "low_stock"
                        ? "fa-box-open"
                        : "fa-clock";
                const action = item.type || "default";

                return `
                    <div class="alert-box ${typeClass}">
                        <div class="alert-icon"><i class="fa-solid ${icon}"></i></div>
                        <div class="alert-content">
                            <h4>${escapeHtml(item.title || "Thông báo")}</h4>
                            <p>${escapeHtml(item.message || "")}</p>
                        </div>
                        <button class="btn-action-small" type="button" data-alert-action="${escapeHtml(action)}">
                            ${escapeHtml(item.action_label || "Xem")}
                        </button>
                    </div>
                `;
            })
            .join("");
    }

    function renderReminders(reminders) {
        if (!upcomingReminderList) {
            return;
        }

        if (!reminders || reminders.length === 0) {
            upcomingReminderList.innerHTML = emptyCard("Bạn chưa có lịch nhắc uống thuốc. Hãy thêm trong mục Tủ Thuốc.");
            return;
        }

        upcomingReminderList.innerHTML = reminders
            .map((item) => {
                const status = item.is_enabled ? "Đang bật" : "Đang tắt";
                return `
                    <div class="medicine-card">
                        <div class="card-left">
                            <div class="icon-box blue"><i class="fa-regular fa-clock"></i></div>
                            <div class="card-info">
                                <h4>${escapeHtml(item.medicine_name || "")}</h4>
                                <p>${escapeHtml(item.frequency_note || "Hằng ngày")} • ${escapeHtml(item.meal_note || "Không ghi chú")}</p>
                            </div>
                        </div>
                        <div class="dashboard-right-col">
                            <span class="card-time">${escapeHtml(item.time_of_day || "--:--")}</span>
                            <span class="status-pill ${item.is_enabled ? "success" : "muted"}">${status}</span>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    function renderHistory(items) {
        if (!recentCheckList) {
            return;
        }

        if (!items || items.length === 0) {
            recentCheckList.innerHTML = emptyCard("Chưa có lịch sử kiểm tra. Hãy thực hiện lần kiểm tra đầu tiên.");
            return;
        }

        recentCheckList.innerHTML = items
            .map((item) => {
                const joined = (item.input_items || []).join(" + ");
                return `
                    <div class="medicine-card">
                        <div class="card-left">
                            <div class="icon-box green"><i class="fa-solid fa-shield-heart"></i></div>
                            <div class="card-info">
                                <h4>${escapeHtml(item.summary_title || "Kết quả kiểm tra")}</h4>
                                <p>${escapeHtml(joined || "Không có dữ liệu")}</p>
                            </div>
                        </div>
                        <div class="dashboard-right-col">
                            <span class="status-pill ${escapeHtml(item.summary_level || "safe")}">${toSummaryLabel(item.summary_level)}</span>
                            <span class="muted-text">${formatDateTime(item.created_at)}</span>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    function handleAlertAction(event) {
        const button = event.target.closest("[data-alert-action]");
        if (!button) {
            return;
        }

        const action = button.dataset.alertAction || "";
        if (action === "interaction") {
            window.location.href = "check.html";
            return;
        }

        window.location.href = "medicines.html";
    }

    async function loadDashboard() {
        showError("");

        if (dashboardAlerts) {
            dashboardAlerts.innerHTML = emptyCard("Đang tải cảnh báo...");
        }
        if (upcomingReminderList) {
            upcomingReminderList.innerHTML = emptyCard("Đang tải lịch nhắc...");
        }
        if (recentCheckList) {
            recentCheckList.innerHTML = emptyCard("Đang tải lịch sử kiểm tra...");
        }

        try {
            const [dashboard, history] = await Promise.all([
                api.getDashboard(),
                api.getCheckHistory(5),
            ]);

            renderAlerts(dashboard.alerts || []);
            renderReminders(dashboard.upcoming_reminders || []);
            renderHistory(history || []);
        } catch (error) {
            showError(error.message || "Không thể tải dữ liệu trang chủ lúc này.");
            renderAlerts([]);
            renderReminders([]);
            renderHistory([]);
        }
    }

    if (heroCheckAction) {
        heroCheckAction.addEventListener("click", function () {
            window.location.href = "check.html";
        });
        heroCheckAction.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = "check.html";
            }
        });
    }

    if (btnQuickCheck) {
        btnQuickCheck.addEventListener("click", function () {
            window.location.href = "check.html";
        });
    }

    if (btnRefreshDashboard) {
        btnRefreshDashboard.addEventListener("click", loadDashboard);
    }

    if (dashboardAlerts) {
        dashboardAlerts.addEventListener("click", handleAlertAction);
    }

    loadDashboard();
});
