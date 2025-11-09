// فتح نافذة الملاحظات لكل طلب
document.querySelectorAll(".btn-note").forEach(btn => {
    btn.addEventListener("click", function() {
        const orderId = this.dataset.id;
        const noteModal = document.getElementById("noteModal");
        const noteInput = noteModal.querySelector("textarea");

        fetch(`/orders/history/${orderId}`)
            .then(res => res.json())
            .then(data => {
                let notesHtml = data.map(h => `<p>${h.timestamp} - ${h.change_type}: ${h.details}</p>`).join("");
                document.getElementById("historyContent").innerHTML = notesHtml;
            });
        noteModal.style.display = "block";
    });
});

// إغلاق النوافذ المنبثقة
document.querySelectorAll(".modal .close").forEach(btn => {
    btn.addEventListener("click", function() {
        this.closest(".modal").style.display = "none";
    });
});
// دالة إظهار المودال
function showModal(modalId) {
  document.getElementById(modalId).classList.add('active');
  document.body.style.overflow = 'hidden';
}

// دالة إخفاء المودال
function hideModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
  document.body.style.overflow = 'auto';
}

// إغلاق المودال عند النقر خارج المحتوى
document.addEventListener('click', function(event) {
  if (event.target.classList.contains('modal')) {
    hideModal(event.target.id);
  }
});