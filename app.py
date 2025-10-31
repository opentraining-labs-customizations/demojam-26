from flask import Flask, render_template, request, jsonify
import json
import re
import uuid
import html
from pathlib import Path

app = Flask(__name__)

# Utility: clean labels to remove *, [, ], and extra whitespace
def clean_label(label):
    """
    Remove unwanted characters like *, [, ] from a label
    and strip extra whitespace.
    """
    import re
    if not label:
        return ""
    cleaned = re.sub(r'[\*\[\]]', '', str(label))  # remove *, [, ]
    cleaned = re.sub(r'\s+', ' ', cleaned)         # replace multiple spaces with one
    return cleaned.strip()

# Utility: generate stable ids for nodes
def nid():
    return str(uuid.uuid4())

# Convert typical Ansible playbook JSON structure to nodes + edges and nested JSON/markdown
def build_mindmap_from_ansible(ansible_json):
    """
    Build hierarchical structure from Ansible playbook JSON or text output.
    Ensures one "Tasks" node per play, with ordered tasks underneath.
    """
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

    # ✅ Add plays
    plays = ansible_json.get("plays", [])
    if isinstance(plays, list) and plays:
        plays_parent = add_node("Plays", parent=root_id, group="plays")
       
        for play_index, play in enumerate(plays, 1):
           play_name = clean_label(play.get("name") or play.get("play", {}).get("name") or f"Play {play_index}")
           play_id = add_node(play_name, parent=plays_parent, group="play")
          
           # ✅ Create one single "Tasks" node per play
           tasks_parent = add_node("Tasks", parent=play_id, group="tasks")
           tasks = play.get("tasks") or play.get("tasks_results") or play.get("tasks_list") or []
           if isinstance(tasks, list) and tasks:
                for task_index, task in enumerate(tasks, 1):
                    # Task name cleanup
                    if isinstance(task, dict):
                        tname = task.get("name") or task.get("task", {}).get("name") or task.get("action") or f"Task {task_index}"
                    else:
                        tname = str(task)
                    tname_clean = clean_label(tname)
                    task_label = f"{task_index:02d}. {tname_clean}"
                    task_id = add_node(task_label, parent=tasks_parent, group="task")

                    # ✅ Attach hosts if any
                    hosts = task.get("hosts") if isinstance(task, dict) else None
                    if hosts and isinstance(hosts, dict):
                        for host, result in hosts.items():
                            host_node = add_node(f"Host: {host}", parent=task_id)
                            if isinstance(result, dict):
                                for k, v in result.items():
                                    if isinstance(v, (str, int, float)):
                                        add_node(f"{k}: {v}", parent=host_node, group="status")

    # ✅ Play Recap
    recap = ansible_json.get("stats") or ansible_json.get("playbook_recap") or {}
    if recap:
        recap_parent = add_node("Play Recap", parent=root_id, group="recap")
        for host, results in recap.items():
            host_id = add_node(f"Host: {host}", parent=recap_parent)
            if isinstance(results, dict):
                for k, v in results.items():
                    add_node(f"{k}: {v}", parent=host_id, group="recap-item")

    # ✅ Build nested JSON (for collapsible frontend)
    id_to_node = {n['id']: {**n, 'children': []} for n in nodes}
    for e in edges:
        id_to_node[e['from']]['children'].append(id_to_node[e['to']])
    nested_json = id_to_node[root_id]

    # ✅ Markdown version
    def to_markdown(node, depth=0):
        indent = "  " * depth
        lines = [f"{indent}- {node['label']}"]
        for c in node.get('children', []):
            lines.extend(to_markdown(c, depth + 1))
        return lines

    markdown = "\n".join(to_markdown(nested_json))

    return {
        "nodes": nodes,
        "edges": edges,
        "nested_json": nested_json,
        "markdown": markdown,
        "status_meanings": status_meanings
    }

def get_top_time_consuming_tasks(ansible_json, top_n=20):
    """
    Extract top N time-consuming tasks from parsed Ansible playbook data.
    Looks for task duration fields such as 'duration', 'duration_seconds', or 'duration::start/end'.
    """

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

            # 🔹 Look for common Ansible duration fields
            if "duration" in task and isinstance(task["duration"], (int, float)):
                duration = float(task["duration"])
            elif "duration_seconds" in task:
                duration = float(task["duration_seconds"])
            elif "duration" in task and isinstance(task["duration"], dict):
                # e.g., {"start": "...", "end": "...", "elapsed": 3.21}
                duration = float(task["duration"].get("elapsed", 0))

            # If no duration recorded, skip
            if duration is None:
                continue

            task_durations.append({
                "play": play_name,
                "task": task_name,
                "duration_seconds": duration
            })

    # Sort tasks descending by duration
    top_tasks = sorted(task_durations, key=lambda x: x["duration_seconds"], reverse=True)[:top_n]
    return top_tasks

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
# ... (existing imports and functions) ...

# 🎯 Define the new route for getting top tasks
@app.route('/top_tasks_analysis', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "no file uploaded"}), 400

    try:
        raw = file.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return jsonify({"error": "failed to read file", "message": str(e)}), 400

    # Very basic parser for text Ansible output
    plays = []
    current_play = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("PLAY ["):
            play_name = line[6:-1]
            current_play = {"name": play_name, "tasks": []}
            plays.append(current_play)
        elif line.startswith("TASK [") and current_play:
            task_name = line[6:-1]
            current_play["tasks"].append({"name": task_name})
        elif line.startswith("PLAY RECAP"):
            break
 
    # Extract recap section
    recap = {}
    recap_started = False
    for line in raw.splitlines():
      if line.startswith("PLAY RECAP"):
          recap_started = True
          continue
     # 🎯 FIX: Only process lines that contain both a host and status metrics (e.g., ok=X)
      if recap_started and line.strip():
        parts = line.split()
        
        # Check if the line has enough parts to be a recap line (Host + at least one stat)
        # And ensure at least one part contains an '=' sign (e.g., ok=13)
        if len(parts) >= 2 and any('=' in part for part in parts[1:]):
            host = parts[0]
            rec = {}
            for kv in parts[1:]:
                if "=" in kv:
                    k, v = kv.split("=")
                    # Optionally convert v to int/string as needed, but for mindmap
                    # visualization, keeping it as string is often simpler.
                    rec[k] = v
            
            # Only add to recap if we actually parsed host stats
            if rec:
                recap[host] = rec
        
        # Stop parsing recap if we encounter a line that is clearly not a recap line
        # This is a heuristic and depends on your specific output format, 
        # but generally recap is the last block.
        # A blank line or a line starting with something else (like "PLAY [...")
        # usually marks the end.
        elif len(parts) < 2: 
             # If it's a blank line or a line that only contains a host with no stats, 
             # stop parsing the recap block.
             recap_started = False 
    # Final parsed data structure
    data = {"plays": plays, "stats": recap}
    # 1. Build mindmap structure
    mind = build_mindmap_from_ansible(data)
    # Run Top Tasks analysis directly using the parsed data
    top_tasks_list = get_top_time_consuming_tasks(data, top_n=20)
    # Add the analysis results to the final JSON response
    mind["top_20_time_consuming_tasks"] = top_tasks_list
    
    # NOTE: You no longer need to include mind["original_ansible_data"] = data 
    # since we are doing the analysis here.
    return jsonify(mind)


if __name__ == '__main__':
    app.run(debug=True)
