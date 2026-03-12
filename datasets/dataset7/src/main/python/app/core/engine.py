"""Core processing engine."""


class ProcessingEngine:
    def __init__(self, config: dict):
        self.config = config
        self.pipeline = []

    def add_stage(self, stage_fn):
        self.pipeline.append(stage_fn)

    def run(self, data):
        result = data
        for stage in self.pipeline:
            result = stage(result)
        return result
