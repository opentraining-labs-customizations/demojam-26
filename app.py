from flask import Flask, render_template, request, jsonify
import json
import re
import uuid
import html
from pathlib import Path
from datetime import timedelta

app = Flask(__name__)

# Utility: clean labels to remove *, [, ], and extra whitespace
def clean_label(label):
    if not label:
        return ""
    cleaned = re.sub(r'[\*\[\]]', '', str(label))
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def nid():
    return str(uuid.uuid4())

def build_mindmap_from_ansible(ansible_json):
    root_id = nid()
    nodes = [{"id": root_id, "label": "Playbook Output", "title": "Root: Playbook Output"}]
    edges = []

    def add_node(label, title=None, parent=None, group=None):
        _id = nid()
        node = {"id": _id, "label": label, "title": title or label}
        if group:
            node["group"] = group
        nodes.append(node)
        if parent:
            edges.append({"from": parent, "to": _id})
        return _id

    status_meanings = {
        "ok": "Task succeeded (no error)",
        "changed": "Task made changes on target host",
        "fatal": "Task failed",
        "skipped": "Task was skipped",
        "unreachable": "Host was unreachable",
        "rescued": "Task failed but rescued by 'rescue' block",
        "ignored": "Failure ignored via 'ignore_errors'"
    }

    plays = ansible_json.get("plays", [])
    if isinstance(plays, list) and plays:
        plays_parent = add_node("Plays", parent=root_id, group="plays")

        for play_index, play in enumerate(plays, 1):
            play_name = clean_label(play.get("name") or play.get("play", {}).get("name") or f"Play {play_index}")
            play_id = add_node(play_name, parent=plays_parent, group="play")

            tasks_parent = add_node("Tasks", parent=play_id, group="tasks")
            tasks = play.get("tasks") or play.get("tasks_results") or play.get("tasks_list") or []
            if isinstance(tasks, list) and tasks:
                for task_index, task in enumerate(tasks, 1):
                    if isinstance(task, dict):
                        tname = task.get("name") or task.get("task", {}).get("name") or task.get("action") or f"Task {task_index}"
                    else:
                        tname = str(task)
                    tname_clean = clean_label(tname)
                    task_label = f"{task_index:02d}. {tname_clean}"
                    task_id = add_node(task_label, parent=tasks_parent, group="task")

                    hosts = task.get("hosts") if isinstance(task, dict) else None
                    if hosts and isinstance(hosts, dict):
                        for host, result in hosts.items():
                            host_node = add_node(f"Host: {host}", parent=task_id)
                            if isinstance(result, dict):
                                for k, v in result.items():
                                    if isinstance(v, (str, int, float)):
                                        add_node(f"{k}: {v}", parent=host_node, group="status")

    recap = ansible_json.get("stats") or ansible_json.get("playbook_recap") or {}
    if recap:
        recap_parent = add_node("Play Recap", parent=root_id, group="recap")
        for host, results in recap.items():
            host_id = add_node(f"Host: {host}", parent=recap_parent)
            if isinstance(results, dict):
                for k, v in results.items():
                    add_node(f"{k}: {v}", parent=host_id, group="recap-item")

    id_to_node = {n['id']: {**n, 'children': []} for n in nodes}
    for e in edges:
        id_to_node[e['from']]['children'].append(id_to_node[e['to']])
    nested_json = id_to_node[root_id]

    def to_markdown(node, depth=0):
        indent = "  " * depth
        lines = [f"{indent}- {node['label']}"]
        for c in node.get('children', []):
            lines.extend(to_markdown(c, depth + 1))
        return lines

    markdown = "\n".join(to_markdown(nested_json))
    return {"nodes": nodes, "edges": edges, "nested_json": nested_json, "markdown": markdown, "status_meanings": status_meanings}


def get_top_time_consuming_tasks(ansible_json, top_n=20):
    task_durations = []
    plays = ansible_json.get("plays", [])
    for play_index, play in enumerate(plays, 1):
        play_name = play.get("name") or f"Play {play_index}"
        tasks = play.get("tasks") or play.get("tasks_results") or play.get("tasks_list") or []

        for task_index, task in enumerate(tasks, 1):
            if not isinstance(task, dict):
                continue
            task_name = task.get("name") or f"Task {task_index}"
            duration = None
            if "duration" in task and isinstance(task["duration"], (int, float)):
                duration = float(task["duration"])
            elif "duration_seconds" in task:
                duration = float(task["duration_seconds"])
            elif "duration" in task and isinstance(task["duration"], dict):
                duration = float(task["duration"].get("elapsed", 0))
            if duration is None:
                continue
            task_durations.append({"play": play_name, "task": task_name, "duration_seconds": duration})
    return sorted(task_durations, key=lambda x: x["duration_seconds"], reverse=True)[:top_n]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/top_tasks_analysis', methods=['POST'])
def top_tasks_analysis():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "no file uploaded"}), 400

    try:
        raw = file.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return jsonify({"error": "failed to read file", "message": str(e)}), 400

    play_pattern = re.compile(r"^PLAY \[(.+?)\]")
    task_pattern = re.compile(r"^TASK \[(.+?)\]")
    time_pattern = re.compile(r"\((\d+):(\d+):(\d+\.\d+)\)")

    plays = []
    current_play = None
    current_task = None

    for line in raw.splitlines():
        line = line.strip()
        play_match = play_pattern.match(line)
        if play_match:
            play_name = play_match.group(1)
            current_play = {"name": play_name, "tasks": []}
            plays.append(current_play)
            continue

        task_match = task_pattern.match(line)
        if task_match and current_play:
            task_name = task_match.group(1)
            current_task = {"name": task_name}
            current_play["tasks"].append(current_task)
            continue

        time_match = time_pattern.search(line)
        if time_match and current_task:
            h, m, s = map(float, time_match.groups())
            duration = timedelta(hours=h, minutes=m, seconds=s).total_seconds()
            current_task["duration_seconds"] = duration
            current_task = None
            continue

        if line.startswith("PLAY RECAP"):
            break

    recap = {}
    recap_started = False
    for line in raw.splitlines():
        if line.startswith("PLAY RECAP"):
            recap_started = True
            continue
        if recap_started and line.strip():
            parts = line.split()
            if len(parts) >= 2 and any('=' in part for part in parts[1:]):
                host = parts[0]
                rec = {}
                for kv in parts[1:]:
                    if "=" in kv:
                        k, v = kv.split("=")
                        rec[k] = v
                if rec:
                    recap[host] = rec
            elif len(parts) < 2:
                recap_started = False

    data = {"plays": plays, "stats": recap}
    mind = build_mindmap_from_ansible(data)
    top_tasks_list = get_top_time_consuming_tasks(data, top_n=20)
    mind["top_20_time_consuming_tasks"] = top_tasks_list

    return jsonify(mind)


if __name__ == '__main__':
    app.run(debug=True)
