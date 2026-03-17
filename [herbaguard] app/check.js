document.addEventListener("DOMContentLoaded", function () {
    const savedMed = localStorage.getItem("searchMedicine");
    if (savedMed) {
        localStorage.removeItem("searchMedicine");
    }

    const inputMed = document.getElementById("medicineInput");
    const btnAdd = document.getElementById("btnAddMedicine");
    const btnClearAll = document.getElementById("btnClearAll");
    const btnCheck = document.getElementById("btnCheckInteraction");
    const medicineList = document.getElementById("medicineList");
    const medCount = document.getElementById("medCount");
    const loadingOverlay = document.getElementById("loadingOverlay");
    const errorBox = document.getElementById("apiError");
    const suggestionsBox = document.getElementById("searchSuggestions");
    const demoChipList = document.getElementById("demoChipList");
    const voiceButton = document.querySelector(".btn-voice");
    const scannerCard = document.querySelector(".scanner-card");

    const state = {
        selectedItems: [],
        isSubmitting: false,
        suggestionTimer: null,
    };

    function normalizeKey(value) {
        return value
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/đ/g, "d")
            .replace(/[^a-z0-9\s]/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function escapeHtml(value) {
        return value
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function showError(message) {
        if (!message) {
            errorBox.textContent = "";
            errorBox.classList.add("hidden");
            return;
        }

        errorBox.textContent = message;
        errorBox.classList.remove("hidden");
    }

    function updateCount() {
        medCount.innerText = String(state.selectedItems.length);
    }

    function renderList() {
        medicineList.innerHTML = "";

        if (state.selectedItems.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty-state";
            empty.textContent = "Chưa có mục nào. Hãy thêm thuốc tây hoặc thảo dược để bắt đầu.";
            medicineList.appendChild(empty);
            updateCount();
            return;
        }

        state.selectedItems.forEach((item) => {
            const card = document.createElement("div");
            card.className = "medicine-card";
            card.dataset.key = item.key;
            card.innerHTML = `
                <div class="card-left">
                    <div class="icon-box blue"><i class="fa-solid fa-capsules"></i></div>
                    <div class="card-info">
                        <h4>${escapeHtml(item.name)}</h4>
                        <p class="input-origin">${escapeHtml(item.source)}</p>
                    </div>
                </div>
                <button class="btn-remove" type="button"><i class="fa-solid fa-xmark"></i></button>
            `;
            medicineList.appendChild(card);
        });

        updateCount();
    }

    function hasItem(name) {
        const key = normalizeKey(name);
        return state.selectedItems.some((item) => item.key === key);
    }

    function addItem(rawName, sourceLabel) {
        const name = rawName.trim();
        if (!name) {
            return;
        }

        if (hasItem(name)) {
            showError(`"${name}" đã có trong danh sách.`);
            return;
        }

        state.selectedItems.push({
            key: normalizeKey(name),
            name: name,
            source: sourceLabel || "Thêm thủ công",
        });

        inputMed.value = "";
        hideSuggestions();
        showError("");
        renderList();
    }

    function removeByKey(key) {
        state.selectedItems = state.selectedItems.filter((item) => item.key !== key);
        renderList();
    }

    function clearAllItems() {
        state.selectedItems = [];
        renderList();
        hideSuggestions();
        showError("");
    }

    function hideSuggestions() {
        suggestionsBox.innerHTML = "";
        suggestionsBox.classList.add("hidden");
    }

    function renderSuggestions(results) {
        if (!results || results.length === 0) {
            hideSuggestions();
            return;
        }

        const rows = results
            .map((result) => {
                const isDirectMatch = normalizeKey(result.canonical_name) === normalizeKey(result.matched_alias);
                const subtitle = isDirectMatch
                    ? "Khớp trực tiếp"
                    : `Khớp theo bí danh: ${result.matched_alias}`;
                const typeLabel = result.type === "drug" ? "Thuốc Tây" : "Thảo Dược";

                return `
                    <button class="suggestion-item" type="button" data-name="${escapeHtml(result.canonical_name)}" data-source="Gợi ý: ${escapeHtml(result.matched_alias)}">
                        <span class="suggestion-main">
                            <strong>${escapeHtml(result.canonical_name)}</strong>
                            <span>${escapeHtml(subtitle)}</span>
                        </span>
                        <span class="suggestion-type ${result.type}">${typeLabel}</span>
                    </button>
                `;
            })
            .join("");

        suggestionsBox.innerHTML = rows;
        suggestionsBox.classList.remove("hidden");
    }

    async function fetchSuggestions() {
        const query = inputMed.value.trim();
        if (query.length < 2 || !window.HerbaGuardAPI) {
            hideSuggestions();
            return;
        }

        try {
            const results = await window.HerbaGuardAPI.search(query);
            if (query !== inputMed.value.trim()) {
                return;
            }
            renderSuggestions(results.slice(0, 10));
        } catch (error) {
            hideSuggestions();
        }
    }

    function debounceSuggestions() {
        if (state.suggestionTimer) {
            clearTimeout(state.suggestionTimer);
        }
        state.suggestionTimer = setTimeout(fetchSuggestions, 220);
    }

    function setSubmitting(isSubmitting) {
        state.isSubmitting = isSubmitting;
        btnCheck.disabled = isSubmitting;
        btnAdd.disabled = isSubmitting;
        inputMed.disabled = isSubmitting;

        if (isSubmitting) {
            loadingOverlay.classList.remove("hidden");
        } else {
            loadingOverlay.classList.add("hidden");
        }
    }

    async function submitCheck() {
        if (state.isSubmitting) {
            return;
        }

        if (state.selectedItems.length < 2) {
            showError("Vui lòng thêm ít nhất 2 mục để kiểm tra tương tác.");
            return;
        }

        if (!window.HerbaGuardAPI || !window.HerbaGuardAPI.checkInteraction) {
            showError("Không thể kết nối API. Vui lòng tải lại trang.");
            return;
        }

        showError("");
        setSubmitting(true);

        try {
            const payload = state.selectedItems.map((item) => item.name);
            const response = await window.HerbaGuardAPI.checkInteraction(payload);
            sessionStorage.setItem("herbaguard:lastResult", JSON.stringify(response));
            window.location.href = "result.html";
        } catch (error) {
            showError(error.message || "Không thể kiểm tra tương tác lúc này. Vui lòng thử lại.");
        } finally {
            setSubmitting(false);
        }
    }

    btnAdd.addEventListener("click", function () {
        addItem(inputMed.value, "Thêm thủ công");
    });

    inputMed.addEventListener("keypress", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            addItem(inputMed.value, "Thêm thủ công");
        }
    });

    inputMed.addEventListener("input", debounceSuggestions);

    suggestionsBox.addEventListener("click", function (event) {
        const target = event.target.closest(".suggestion-item");
        if (!target) {
            return;
        }

        const suggestedName = target.dataset.name || "";
        const source = target.dataset.source || "Gợi ý từ hệ thống";
        addItem(suggestedName, source);
    });

    document.addEventListener("click", function (event) {
        if (!event.target.closest(".search-wrapper")) {
            hideSuggestions();
        }
    });

    btnClearAll.addEventListener("click", clearAllItems);

    medicineList.addEventListener("click", function (event) {
        const removeButton = event.target.closest(".btn-remove");
        if (!removeButton) {
            return;
        }

        const card = removeButton.closest(".medicine-card");
        if (!card || !card.dataset.key) {
            return;
        }

        removeByKey(card.dataset.key);
    });

    demoChipList.addEventListener("click", function (event) {
        const chip = event.target.closest(".demo-chip");
        if (!chip) {
            return;
        }
        addItem(chip.dataset.item || "", "Thêm từ gợi ý demo");
    });

    if (voiceButton) {
        voiceButton.addEventListener("click", function () {
            showError("Demo hiện chưa hỗ trợ nhập giọng nói. Vui lòng nhập thủ công.");
        });
    }

    if (scannerCard) {
        scannerCard.addEventListener("click", function () {
            showError("OCR chưa được bật trong bản demo local. Vui lòng nhập thủ công để đảm bảo chính xác.");
        });
    }

    btnCheck.addEventListener("click", submitCheck);

    if (savedMed) {
        addItem(savedMed, "Từ trang chủ");
    }

    renderList();
});
