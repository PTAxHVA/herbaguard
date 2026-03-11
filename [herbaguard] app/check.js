document.addEventListener("DOMContentLoaded", function() {
    // 1. Nhận tên thuốc từ trang chủ (nếu có)
    const savedMed = localStorage.getItem("searchMedicine");
    if (savedMed) {
        document.getElementById('medicineInput').value = savedMed;
        localStorage.removeItem("searchMedicine");
    }

    // 2. Gán sự kiện cho các nút bằng ID thay vì onclick trong HTML
    const btnAdd = document.getElementById('btnAddMedicine');
    const inputMed = document.getElementById('medicineInput');
    const btnClearAll = document.getElementById('btnClearAll');
    const btnCheck = document.getElementById('btnCheckInteraction');

    // Hàm cập nhật số lượng
    function updateCount() {
        document.getElementById('medCount').innerText = document.getElementById('medicineList').children.length;
    }

    // Thêm thuốc mới
    function addMedicine() {
        const medName = inputMed.value.trim();
        if (medName === "") return;

        const list = document.getElementById('medicineList');
        const newCard = document.createElement('div');
        newCard.className = "medicine-card";
        newCard.innerHTML = `
            <div class="card-left">
                <div class="icon-box blue"><i class="fa-solid fa-pills"></i></div>
                <div class="card-info">
                    <h4>${medName}</h4>
                    <p>Thêm thủ công</p>
                </div>
            </div>
            <button class="btn-remove"><i class="fa-solid fa-xmark"></i></button>
        `;
        list.appendChild(newCard);
        inputMed.value = "";
        updateCount();
    }

    // Gắn sự kiện Thêm
    if(btnAdd) btnAdd.addEventListener('click', addMedicine);
    if(inputMed) {
        inputMed.addEventListener("keypress", function(e) {
            if (e.key === "Enter") { e.preventDefault(); addMedicine(); }
        });
    }

    // Xóa tất cả
    if(btnClearAll) {
        btnClearAll.addEventListener('click', function() {
            document.getElementById('medicineList').innerHTML = '';
            updateCount();
        });
    }

    // Xóa từng cái (Dùng Event Delegation vì thẻ thuốc được tạo ra linh động)
    document.getElementById('medicineList').addEventListener('click', function(e) {
        // Tìm button chứa class btn-remove hoặc thẻ i bên trong nó
        if(e.target.closest('.btn-remove')) {
            e.target.closest('.medicine-card').remove();
            updateCount();
        }
    });

    // Kiểm tra tương tác
    if(btnCheck) {
        btnCheck.addEventListener('click', function() {
            const medCount = document.getElementById('medicineList').children.length;
            if (medCount < 2) {
                alert("Vui lòng thêm ít nhất 2 loại thuốc để AI có thể kiểm tra tương tác!");
                return;
            }
            document.getElementById('loadingOverlay').classList.remove('hidden');
            setTimeout(() => { window.location.href = 'result.html'; }, 2000);
        });
    }
});