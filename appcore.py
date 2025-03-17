# appcore.py
import uuid
from datetime import datetime
import xml.etree.ElementTree as ET
from PySide6.QtCore import QObject, Signal
"""still needs to be tested and edited
"""
class Task(QObject):
    updated = Signal()

    def __init__(self, title="", description="", assignees=None, due_date=None):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.title = title
        self.description = description
        self.assignees = assignees if assignees else []
        self.due_date = due_date
        self.created_at = datetime.now()
        self.history = []

    def add_movement(self, from_column, to_column):
        entry = {
            "timestamp": datetime.now(),
            "from": from_column,
            "to": to_column
        }
        self.history.append(entry)
        self.updated.emit()


class Column(QObject):
    updated = Signal()

    def __init__(self, name, wip_limit=0):
        super().__init__()
        self.name = name
        self.wip_limit = wip_limit
        self.tasks = []

    def add_task(self, task):
        if self.wip_limit > 0 and len(self.tasks) >= self.wip_limit:
            return False
        self.tasks.append(task)
        self.updated.emit()
        return True

    def remove_task(self, task):
        if task in self.tasks:
            self.tasks.remove(task)
            self.updated.emit()
            return True
        return False


class Project(QObject):
    project_updated = Signal()

    def __init__(self, name="New Project"):
        super().__init__()
        self.name = name
        self.columns = []
        self.tasks = []
        self.file_path = None
        self._default_columns = ["Backlog", "In Progress", "Review", "Done"]

        for col_name in self._default_columns:
            self.columns.append(Column(col_name))

    def create_task(self, **kwargs):
        task = Task(**kwargs)
        self.tasks.append(task)
        self.columns[0].add_task(task)
        task.updated.connect(self._auto_save)
        self.project_updated.emit()
        return task

    def move_task(self, task, from_col_idx, to_col_idx):
        from_col = self.columns[from_col_idx]
        to_col = self.columns[to_col_idx]

        if from_col.remove_task(task):
            success = to_col.add_task(task)
            if success:
                task.add_movement(from_col.name, to_col.name)
                self.project_updated.emit()
                return True
            from_col.add_task(task)  # Revert if WIP limit exceeded
        return False

    def _auto_save(self):
        if self.file_path:
            self.save_to_xml(self.file_path)

    # Persistence methods
    def save_to_xml(self, file_path):
        root = ET.Element("KanbanProject", name=self.name)

        columns_elem = ET.SubElement(root, "Columns")
        for column in self.columns:
            col_elem = ET.SubElement(columns_elem, "Column",
                                     name=column.name,
                                     wip_limit=str(column.wip_limit))

        tasks_elem = ET.SubElement(root, "Tasks")
        for task in self.tasks:
            task_elem = ET.SubElement(tasks_elem, "Task", id=task.id)
            ET.SubElement(task_elem, "Title").text = task.title
            ET.SubElement(task_elem, "Description").text = task.description
            ET.SubElement(
                task_elem, "CreatedAt").text = task.created_at.isoformat()

            if task.due_date:
                ET.SubElement(
                    task_elem, "DueDate").text = task.due_date.isoformat()

            assignees_elem = ET.SubElement(task_elem, "Assignees")
            for assignee in task.assignees:
                ET.SubElement(assignees_elem, "Assignee").text = assignee

            history_elem = ET.SubElement(task_elem, "History")
            for entry in task.history:
                hist_entry = ET.SubElement(history_elem, "Entry")
                ET.SubElement(
                    hist_entry, "Timestamp").text = entry["timestamp"].isoformat()
                ET.SubElement(hist_entry, "From").text = entry["from"]
                ET.SubElement(hist_entry, "To").text = entry["to"]

        ET.ElementTree(root).write(
            file_path, encoding="utf-8", xml_declaration=True)
        self.file_path = file_path

    @classmethod
    def load_from_xml(cls, file_path):
        tree = ET.parse(file_path)
        root = tree.getroot()

        project = cls(root.get("name"))
        project.file_path = file_path
        project.columns.clear()

        # Load columns
        for col_elem in root.find("Columns").findall("Column"):
            project.columns.append(Column(
                name=col_elem.get("name"),
                wip_limit=int(col_elem.get("wip_limit", 0))
            ))

        # Load tasks
        tasks = []
        task_map = {}
        for task_elem in root.find("Tasks").findall("Task"):
            task = Task()
            task.id = task_elem.get("id")
            task.title = task_elem.findtext("Title")
            task.description = task_elem.findtext("Description")
            task.created_at = datetime.fromisoformat(
                task_elem.findtext("CreatedAt"))

            if task_elem.findtext("DueDate"):
                task.due_date = datetime.fromisoformat(
                    task_elem.findtext("DueDate"))

            task.assignees = [a.text for a in task_elem.find(
                "Assignees").findall("Assignee")]

            history = task_elem.find("History")
            if history:
                for entry in history.findall("Entry"):
                    task.history.append({
                        "timestamp": datetime.fromisoformat(entry.findtext("Timestamp")),
                        "from": entry.findtext("From"),
                        "to": entry.findtext("To")
                    })

            tasks.append(task)
            task_map[task.id] = task
            task.updated.connect(project._auto_save)

        # Rebuild task-column relationships
        for task in tasks:
            if task.history:
                last_move = task.history[-1]
                target_col = next(
                    (c for c in project.columns if c.name == last_move["to"]), None)
                if target_col:
                    target_col.add_task(task)
            else:
                project.columns[0].add_task(task)

        project.tasks = tasks
        return project


class KanbanBoard(QObject):
    current_project_changed = Signal()

    def __init__(self):
        super().__init__()
        self.projects = []
        self.current_project = None

    def create_project(self, name):
        project = Project(name)
        self.projects.append(project)
        self.current_project = project
        self.current_project_changed.emit()
        return project

    def open_project(self, file_path):
        project = Project.load_from_xml(file_path)
        self.projects.append(project)
        self.current_project = project
        self.current_project_changed.emit()
        return project
