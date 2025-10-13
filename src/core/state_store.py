import json, os

class JsonState:
    def __init__(self, path: str = 'state.json'):
        self.path = path
        if not os.path.exists(self.path):
            self.save({'open_orders': {}, 'positions': {}, 'mode': 'PAUSE', 'pnl': {'realized': 0.0}})

    def load(self):
        with open(self.path, 'r') as f:
            return json.load(f)

    def save(self, data):
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
