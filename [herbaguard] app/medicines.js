document.addEventListener("DOMContentLoaded", function () {
    const api = window.HerbaGuardAPI;
    if (!api) {
        return;
    }

    const medicineForm = document.getElementById("medicineForm");
    const medicineIdEl = document.getElementById("medicineId");
    const medicineNameEl = document.getElementById("medicineName");
    const medicineKindEl = document.getElementById("medicineKind");
    const medicineDosageEl = document.getElementById("medicineDosage");
    const medicineStockEl = document.getElementById("medicineStock");
    const medicineInstructionsEl = document.getElementById("medicineInstructions");
    const btnCancelMedicineEdit = document.getElementById("btnCancelMedicineEdit");
    const btnFocusMedicineForm = document.getElementById("btnFocusMedicineForm");
    const medicineFormMsg = document.getElementById("medicineFormMsg");
    const medicineListEl = document.getElementById("medicineList");
    const medicineCountBadge = document.getElementById("medicineCountBadge");

    const reminderForm = document.getElementById("reminderForm");
    const reminderIdEl = document.getElementById("reminderId");
    const reminderMedicineEl = document.getElementById("reminderMedicine");
    const reminderTimeEl = document.getElementById("reminderTime");
    const reminderFrequencyEl = document.getElementById("reminderFrequency");
    const reminderMealNoteEl = document.getElementById("reminderMealNote");
    const reminderEnabledEl = document.getElementById("reminderEnabled");
    const btnCancelReminderEdit = document.getElementById("btnCancelReminderEdit");
    const reminderFormMsg = document.getElementById("reminderFormMsg");
    const reminderListEl = document.getElementById("reminderList");
    const reminderCountBadge = document.getElementById("reminderCountBadge");

    const btnExportMedicinePdf = document.getElementById("btnExportMedicinePdf");

    const state = {
        medicines: [],
        reminders: [],
        loading: false,
    };

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function showFormMessage(element, type, message) {
        if (!element) {
            return;
        }

        if (!message) {
            element.textContent = "";
            element.className = "status-message hidden";
            return;
        }

        element.textContent = message;
        element.className = `status-message ${type}`;
    }

    function setBusy(isBusy) {
        state.loading = isBusy;
        const controls = document.querySelectorAll("button, input, select, textarea");
        controls.forEach((control) => {
            if (control.id === "btn-notification") {
                return;
            }
            control.disabled = isBusy;
        });
    }

    function kindLabel(kind) {
        if (kind === "drug") {
            return "Thuốc Tây";
        }
        if (kind === "herb") {
            return "Thảo Dược";
        }
        return "Chưa rõ";
    }

    function emptyCard(text) {
        return `<div class="empty-state">${escapeHtml(text)}</div>`;
    }

    function formatDateTime(isoText) {
        if (!isoText) {
            return "Không rõ";
        }
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
    }

    function resetMedicineForm() {
        medicineIdEl.value = "";
        medicineNameEl.value = "";
        medicineKindEl.value = "unknown";
        medicineDosageEl.value = "";
        medicineStockEl.value = "0";
        medicineInstructionsEl.value = "";
        showFormMessage(medicineFormMsg, "", "");
    }

    function resetReminderForm() {
        reminderIdEl.value = "";
        reminderTimeEl.value = "08:00";
        reminderFrequencyEl.value = "Hằng ngày";
        reminderMealNoteEl.value = "";
        reminderEnabledEl.checked = true;
        showFormMessage(reminderFormMsg, "", "");
    }

    function renderMedicineOptions() {
        if (!reminderMedicineEl) {
            return;
        }

        if (state.medicines.length === 0) {
            reminderMedicineEl.innerHTML = '<option value="">Chưa có mục nào</option>';
            reminderMedicineEl.value = "";
            return;
        }

        const current = reminderMedicineEl.value;
        reminderMedicineEl.innerHTML = state.medicines
            .map((item) => `<option value="${item.id}">${escapeHtml(item.name)} (${kindLabel(item.kind)})</option>`)
            .join("");

        if (current && state.medicines.some((item) => String(item.id) === current)) {
            reminderMedicineEl.value = current;
        }
    }

    function renderMedicines() {
        if (!medicineListEl) {
            return;
        }

        if (medicineCountBadge) {
            medicineCountBadge.textContent = `${state.medicines.length} mục`;
        }

        if (state.medicines.length === 0) {
            medicineListEl.innerHTML = emptyCard("Chưa có mục nào trong tủ thuốc.");
            return;
        }

        medicineListEl.innerHTML = state.medicines
            .map((item) => {
                const lowStock = Number(item.stock_count) <= 5;
                const reminderCount = state.reminders.filter((reminder) => reminder.medicine_id === item.id).length;

                return `
                    <div class="medicine-card medicine-card-stack" data-medicine-id="${item.id}">
                        <div class="medicine-row-top">
                            <div class="card-left">
                                <div class="icon-box ${item.kind === "herb" ? "green" : "blue"}">
                                    <i class="fa-solid ${item.kind === "herb" ? "fa-leaf" : "fa-capsules"}"></i>
                                </div>
                                <div class="card-info">
                                    <h4>${escapeHtml(item.name)}</h4>
                                    <p>${escapeHtml(item.dosage || "Chưa có liều dùng")} • ${escapeHtml(item.instructions || "Chưa có hướng dẫn")}</p>
                                    <div class="reminder-meta">
                                        <span class="status-tag ${escapeHtml(item.kind || "unknown")}">${kindLabel(item.kind)}</span>
                                        <span class="status-pill ${lowStock ? "warning" : "safe"}">Tồn kho: ${Number(item.stock_count || 0)}</span>
                                        <span class="status-pill muted">${reminderCount} lịch nhắc</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        ${lowStock ? '<span class="stock-warning"><i class="fa-solid fa-triangle-exclamation"></i> Sắp hết thuốc/thảo dược</span>' : ""}

                        <div class="item-action-row">
                            <button class="btn-icon btn-edit" type="button" data-action="edit-medicine" data-id="${item.id}">
                                <i class="fa-solid fa-pen"></i> Sửa
                            </button>
                            <button class="btn-icon btn-delete" type="button" data-action="delete-medicine" data-id="${item.id}">
                                <i class="fa-solid fa-trash"></i> Xóa
                            </button>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    function renderReminders() {
        if (!reminderListEl) {
            return;
        }

        if (reminderCountBadge) {
            reminderCountBadge.textContent = `${state.reminders.length} lịch`;
        }

        if (state.reminders.length === 0) {
            reminderListEl.innerHTML = emptyCard("Chưa có lịch nhắc. Hãy tạo lịch nhắc để theo dõi dùng thuốc.");
            return;
        }

        reminderListEl.innerHTML = state.reminders
            .map((item) => {
                return `
                    <div class="medicine-card medicine-card-stack" data-reminder-id="${item.id}">
                        <div class="medicine-row-top">
                            <div class="card-left">
                                <div class="icon-box blue"><i class="fa-regular fa-clock"></i></div>
                                <div class="card-info">
                                    <h4>${escapeHtml(item.medicine_name)}</h4>
                                    <p>${escapeHtml(item.frequency_note || "Hằng ngày")} • ${escapeHtml(item.meal_note || "Không ghi chú")}</p>
                                    <div class="reminder-meta">
                                        <span class="status-pill ${item.is_enabled ? "success" : "muted"}">${item.is_enabled ? "Đang bật" : "Đang tắt"}</span>
                                        <span class="status-pill safe">Lần tới: ${formatDateTime(item.next_due_iso)}</span>
                                    </div>
                                </div>
                            </div>
                            <span class="card-time">${escapeHtml(item.time_of_day)}</span>
                        </div>

                        <div class="item-action-row">
                            <button class="btn-icon btn-edit" type="button" data-action="edit-reminder" data-id="${item.id}">
                                <i class="fa-solid fa-pen"></i> Sửa
                            </button>
                            <button class="btn-icon btn-delete" type="button" data-action="delete-reminder" data-id="${item.id}">
                                <i class="fa-solid fa-trash"></i> Xóa
                            </button>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    function loadMedicineIntoForm(id) {
        const item = state.medicines.find((medicine) => medicine.id === id);
        if (!item) {
            return;
        }

        medicineIdEl.value = String(item.id);
        medicineNameEl.value = item.name || "";
        medicineKindEl.value = item.kind || "unknown";
        medicineDosageEl.value = item.dosage || "";
        medicineStockEl.value = String(item.stock_count || 0);
        medicineInstructionsEl.value = item.instructions || "";
        showFormMessage(medicineFormMsg, "success", "Đang chỉnh sửa mục đã chọn.");
        medicineNameEl.focus();
    }

    function loadReminderIntoForm(id) {
        const item = state.reminders.find((reminder) => reminder.id === id);
        if (!item) {
            return;
        }

        reminderIdEl.value = String(item.id);
        reminderMedicineEl.value = String(item.medicine_id);
        reminderTimeEl.value = item.time_of_day || "08:00";
        reminderFrequencyEl.value = item.frequency_note || "Hằng ngày";
        reminderMealNoteEl.value = item.meal_note || "";
        reminderEnabledEl.checked = !!item.is_enabled;
        showFormMessage(reminderFormMsg, "success", "Đang chỉnh sửa lịch nhắc đã chọn.");
        reminderTimeEl.focus();
    }

    async function refreshData() {
        setBusy(true);
        try {
            const [medicines, reminders] = await Promise.all([
                api.listMedicines(),
                api.listReminders(),
            ]);
            state.medicines = medicines;
            state.reminders = reminders;

            renderMedicineOptions();
            renderMedicines();
            renderReminders();
        } catch (error) {
            showFormMessage(medicineFormMsg, "error", error.message || "Không thể tải tủ thuốc.");
            showFormMessage(reminderFormMsg, "error", error.message || "Không thể tải lịch nhắc.");
        } finally {
            setBusy(false);
        }
    }

    async function handleMedicineSubmit(event) {
        event.preventDefault();
        if (state.loading) {
            return;
        }

        const name = medicineNameEl.value.trim();
        if (!name) {
            showFormMessage(medicineFormMsg, "error", "Vui lòng nhập tên thuốc/thảo dược.");
            return;
        }

        const stockRaw = Number.parseInt(medicineStockEl.value, 10);
        const payload = {
            name: name,
            kind: medicineKindEl.value || "unknown",
            dosage: medicineDosageEl.value.trim(),
            instructions: medicineInstructionsEl.value.trim(),
            stock_count: Number.isNaN(stockRaw) || stockRaw < 0 ? 0 : stockRaw,
        };

        const editingId = Number.parseInt(medicineIdEl.value, 10);

        setBusy(true);
        try {
            if (editingId > 0) {
                await api.updateMedicine(editingId, payload);
                showFormMessage(medicineFormMsg, "success", "Đã cập nhật mục thành công.");
            } else {
                await api.createMedicine(payload);
                showFormMessage(medicineFormMsg, "success", "Đã thêm mục mới vào tủ thuốc.");
            }

            resetMedicineForm();
            await refreshData();
        } catch (error) {
            showFormMessage(medicineFormMsg, "error", error.message || "Không thể lưu mục này.");
        } finally {
            setBusy(false);
        }
    }

    async function handleReminderSubmit(event) {
        event.preventDefault();
        if (state.loading) {
            return;
        }

        if (state.medicines.length === 0) {
            showFormMessage(reminderFormMsg, "error", "Bạn cần thêm mục trong tủ thuốc trước khi tạo lịch nhắc.");
            return;
        }

        const medicineId = Number.parseInt(reminderMedicineEl.value, 10);
        if (!medicineId) {
            showFormMessage(reminderFormMsg, "error", "Vui lòng chọn thuốc/thảo dược cho lịch nhắc.");
            return;
        }

        const payload = {
            medicine_id: medicineId,
            time_of_day: reminderTimeEl.value,
            frequency_note: reminderFrequencyEl.value.trim() || "Hằng ngày",
            meal_note: reminderMealNoteEl.value.trim(),
            is_enabled: reminderEnabledEl.checked,
        };

        const editingId = Number.parseInt(reminderIdEl.value, 10);

        setBusy(true);
        try {
            if (editingId > 0) {
                await api.updateReminder(editingId, payload);
                showFormMessage(reminderFormMsg, "success", "Đã cập nhật lịch nhắc.");
            } else {
                await api.createReminder(payload);
                showFormMessage(reminderFormMsg, "success", "Đã thêm lịch nhắc mới.");
            }

            resetReminderForm();
            await refreshData();
        } catch (error) {
            showFormMessage(reminderFormMsg, "error", error.message || "Không thể lưu lịch nhắc.");
        } finally {
            setBusy(false);
        }
    }

    async function handleMedicineListClick(event) {
        const actionButton = event.target.closest("[data-action]");
        if (!actionButton || state.loading) {
            return;
        }

        const action = actionButton.dataset.action;
        const id = Number.parseInt(actionButton.dataset.id, 10);
        if (!id) {
            return;
        }

        if (action === "edit-medicine") {
            loadMedicineIntoForm(id);
            return;
        }

        if (action === "delete-medicine") {
            const confirmed = window.confirm("Bạn có chắc muốn xóa mục này? Các lịch nhắc liên quan cũng sẽ bị xóa.");
            if (!confirmed) {
                return;
            }

            setBusy(true);
            try {
                await api.deleteMedicine(id);
                resetMedicineForm();
                resetReminderForm();
                await refreshData();
                showFormMessage(medicineFormMsg, "success", "Đã xóa mục khỏi tủ thuốc.");
            } catch (error) {
                showFormMessage(medicineFormMsg, "error", error.message || "Không thể xóa mục này.");
            } finally {
                setBusy(false);
            }
        }
    }

    async function handleReminderListClick(event) {
        const actionButton = event.target.closest("[data-action]");
        if (!actionButton || state.loading) {
            return;
        }

        const action = actionButton.dataset.action;
        const id = Number.parseInt(actionButton.dataset.id, 10);
        if (!id) {
            return;
        }

        if (action === "edit-reminder") {
            loadReminderIntoForm(id);
            return;
        }

        if (action === "delete-reminder") {
            const confirmed = window.confirm("Bạn có chắc muốn xóa lịch nhắc này?");
            if (!confirmed) {
                return;
            }

            setBusy(true);
            try {
                await api.deleteReminder(id);
                resetReminderForm();
                await refreshData();
                showFormMessage(reminderFormMsg, "success", "Đã xóa lịch nhắc.");
            } catch (error) {
                showFormMessage(reminderFormMsg, "error", error.message || "Không thể xóa lịch nhắc.");
            } finally {
                setBusy(false);
            }
        }
    }

    if (medicineForm) {
        medicineForm.addEventListener("submit", handleMedicineSubmit);
    }

    if (reminderForm) {
        reminderForm.addEventListener("submit", handleReminderSubmit);
    }

    if (btnCancelMedicineEdit) {
        btnCancelMedicineEdit.addEventListener("click", resetMedicineForm);
    }

    if (btnCancelReminderEdit) {
        btnCancelReminderEdit.addEventListener("click", resetReminderForm);
    }

    if (medicineListEl) {
        medicineListEl.addEventListener("click", handleMedicineListClick);
    }

    if (reminderListEl) {
        reminderListEl.addEventListener("click", handleReminderListClick);
    }

    if (btnFocusMedicineForm) {
        btnFocusMedicineForm.addEventListener("click", function () {
            medicineNameEl.focus();
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    if (btnExportMedicinePdf) {
        btnExportMedicinePdf.addEventListener("click", function () {
            window.print();
        });
    }

    resetMedicineForm();
    resetReminderForm();
    refreshData();
});
