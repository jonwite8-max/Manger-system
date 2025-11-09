import os

structure = {
    "templates": [
        "login.html",
        "dashboard.html",
        "orders.html",
        "workers.html",
        "purchases.html",
        "debts.html",
        "transport.html",
        "stats.html"
    ],
    "static": [
        "style.css",
        "script.js"
    ],
    "data": [],
}

for folder, files in structure.items():
    os.makedirs(folder, exist_ok=True)
    for file in files:
        with open(os.path.join(folder, file), "w", encoding="utf-8") as f:
            f.write("<!-- " + file + " -->\n")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(
        "# Flask main application file\n\n"
        "from flask import Flask, render_template\n\n"
        "app = Flask(__name__)\n\n"
        "@app.route('/')\n"
        "def home():\n"
        "    return render_template('dashboard.html')\n\n"
        "if __name__ == '__main__':\n"
        "    app.run(debug=True)\n"
    )

print('✅ تم إنشاء ملفات المشروع بنجاح!')
