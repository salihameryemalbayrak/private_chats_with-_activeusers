from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO, emit
from datetime import datetime
import uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)

users = {}  
rooms = {}  
active_users = {} 
room_active_users = {}  # Her odada hangi kullanıcıların aktif olduğunu takip eder.

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        if "register" in request.form:
            username = request.form.get("username")
            if username in (user["username"] for user in users.values()):
                return render_template("home.html", error="Bu kullanıcı adı zaten mevcut.")
            user_id = str(uuid.uuid4())
            users[user_id] = {"username": username}
            return render_template("home.html", success="Kayıt başarılı! Giriş yapabilirsiniz.")

        elif "login" in request.form:
            username = request.form.get("username")
            user = next((uid for uid, u in users.items() if u["username"] == username), None)
            if not user:
                return render_template("home.html", error="Kullanıcı bulunamadı.")
            session["user_id"] = user
            session["username"] = username
            return redirect(url_for("user_list"))

    return render_template("home.html")

@app.route("/user_list")
def user_list():
    if "username" not in session:
        return redirect(url_for("home"))

    other_users = {uid: u["username"] for uid, u in users.items() if uid != session["user_id"]}
    return render_template("user_list.html", users=other_users, username=session["username"], active_users=active_users)

@app.route("/private_chat/<target_user_id>")
def private_chat(target_user_id):
    if "username" not in session:
        return redirect(url_for("home"))

    if target_user_id not in users:
        return redirect(url_for("user_list"))

    room_id = f"{min(session['user_id'], target_user_id)}-{max(session['user_id'], target_user_id)}"
    if room_id not in rooms:
        rooms[room_id] = []

    session["room_id"] = room_id
    target_username = users[target_user_id]["username"]
    messages = rooms[room_id]
    return render_template("private_chat.html", room_id=room_id, messages=messages, target_user=target_username)

@socketio.on("connect")
def handle_connect():
    user_id = session.get("user_id")
    username = session.get("username")
    if user_id and username:
        active_users[user_id] = username
        socketio.emit("active_users", active_users)

@socketio.on("disconnect")
def handle_disconnect():
    user_id = session.get("user_id")
    room_id = session.get("room_id")
    if user_id in active_users:
        active_users.pop(user_id)
        socketio.emit("active_users", active_users)
    if room_id and user_id in room_active_users.get(room_id, []):
        room_active_users[room_id].remove(user_id)

@socketio.on("message")
def handle_message(data):
    room_id = session.get("room_id")
    if not room_id:
        return

    # Oda ID'sinden alıcıyı belirle
    user_ids = room_id.split("-")

       # Gönderen kimliği, session içindeki kullanıcı kimliği
    sender_user_id = session["user_id"]

    # Alıcıyı belirle: Gönderenin dışındaki kullanıcı
    target_user_id = user_ids[1] if user_ids[1] == sender_user_id else user_ids[0]

    # Mesaj verisini oluştur ve alıcıyı ekle
    message_data = {
        "name": session["username"],
        "receiver": target_user_id,  # Alıcı bilgisi
        "message": data["message"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Gönderildi"
    }

    # Mesajı depola
    rooms[room_id].append(message_data)

    # Mesajı tüm oda üyelerine gönder
    send(message_data, to=room_id)
    emit("message_status_update", message_data, to=room_id)


@socketio.on("join")
def on_join():
    room_id = session.get("room_id")
    user_id = session.get("user_id")
    if not room_id:
        return
    join_room(room_id)

    # Kullanıcıyı aktif olarak oda listesine ekleyelim
    if room_id not in room_active_users:
        room_active_users[room_id] = []
    room_active_users[room_id].append(user_id)

    # Odadaki mesajları güncelleyerek "Görüldü" durumuna çekeriz
    for message in rooms[room_id]:
        message["status"] = "Görüldü"
        socketio.emit("message_status_update", message, room=room_id)

    send({"name": session["username"], "message": "sohbete katıldı"}, to=room_id)

@socketio.on("broadcast_message")
def handle_broadcast_message(data):
    message_data = {
        "name": session["username"],
        "message": data["message"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    for user_id in active_users:
        room_id = f"{min(session['user_id'], user_id)}-{max(session['user_id'], user_id)}"
        rooms.setdefault(room_id, []).append(message_data)
        socketio.emit("message", message_data, room=room_id)

if __name__ == "__main__":
    socketio.run(app, debug=True)
