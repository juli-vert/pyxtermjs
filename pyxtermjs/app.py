#!/usr/bin/env python3
import argparse
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room
import json
import pty
import os
import subprocess
import select
import termios
import struct
import fcntl
import shlex
import logging
import sys

logging.getLogger("werkzeug").setLevel(logging.ERROR)

__version__ = "0.6.0.1"

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = "secret!"
app.config['sessions'] = {}
socketio = SocketIO(app, manage_session=False)


def set_winsize(fd, row, col, xpix=0, ypix=0):
    logging.debug("setting window size with termios")
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    while True:
        socketio.sleep(0.01)
        if app.config["sessions"]:
            timeout_sec = 0
            sessions_to_be_cleaned = []
            for session in app.config["sessions"]:
                (data_ready, _, _) = select.select([app.config["sessions"][session]["fd"]], [], [], timeout_sec)
                if data_ready:
                    output = ""
                    try:
                        output = os.read(app.config["sessions"][session]["fd"], max_read_bytes).decode(errors="ignore")
                    except OSError as err:
                        logging.info("Session has been disconnected")
                    finally:
                        if output == "":
                            sessions_to_be_cleaned.append(session)
                            output = "connection closed"
                            socketio.emit("pty-output", {"output": output}, namespace="/pty", to=session)
                        else:
                            socketio.emit("pty-output", {"output": output}, namespace="/pty", to=session)
            for ses in sessions_to_be_cleaned:
                app.config["sessions"].pop(ses)


@app.route("/console")
def index():
    return render_template("index.html")


@socketio.on("pty-input", namespace="/pty")
def pty_input(data):
    """write to the child pty. The pty sees this as if you are typing in a real
    terminal.
    """
    if app.config["sessions"]:
        logging.debug("received input from browser: %s" % data["input"])
        os.write(app.config["sessions"][request.sid]["fd"], data["input"].encode())


@socketio.on("resize", namespace="/pty")
def resize(data):
    if app.config["sessions"]:
        logging.debug(f"Resizing window to {data['rows']}x{data['cols']}")
        set_winsize(app.config["sessions"][request.sid]["fd"], data["rows"], data["cols"])


@socketio.on("container", namespace="/pty")
def connect(data):
    """new client connected"""
    logging.info(f"new client connected: {json.dumps(data)} with id: {request.sid}")
    if len(app.config["sessions"]) > 6:
        # MAX console number is 6
        return

    # create child process attached to a pty we can read from and write to
    (child_pid, fd) = pty.fork()
    logging.info(f"New child process created: {child_pid}")
    if child_pid == 0:
        # this is the child process fork.
        # anything printed here will show up in the pty, including the output
        # of this subprocess
        spcmd = app.config["cmd"]
        spcmd.append(data['container'])
        spcmd.append(app.config['prompt'])
        subprocess.run(spcmd)
    else:
        # this is the parent process fork.
        # store child fd and pid
        app.config["sessions"].update({request.sid : {"fd": fd, "chid": child_pid}})
        #join_room(request.sid)
        set_winsize(fd, 50, 50)
        cmd = " ".join(shlex.quote(c) for c in app.config["cmd"])
        cmd = f"{cmd} {data['container']} {app.config['prompt']}"
        # logging/print statements must go after this because... I have no idea why
        # but if they come before the background task never starts
        socketio.start_background_task(target=read_and_forward_pty_output)

        logging.info("child pid is " + str(child_pid))
        logging.info(
            f"starting background task with command `{cmd}` to continously read "
            "and forward pty output to client"
        )
        logging.info("task started")


def main():
    
    app.config["cmd"] = ["docker", "exec", "-it"]
    app.config["prompt"] = "bash"
    green = "\033[92m"
    end = "\033[0m"
    log_format = (
        green
        + "pyxtermjs > "
        + end
        + "%(levelname)s (%(funcName)s:%(lineno)s) %(message)s"
    )
    logging.basicConfig(
        format=log_format,
        stream=sys.stdout,
        level=logging.INFO,
    )
    logging.info(f"serving on http://0.0.0.0:5000")
    socketio.run(app, debug=False, port=5000, host="0.0.0.0")


if __name__ == "__main__":
    main()
