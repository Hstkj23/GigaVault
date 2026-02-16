"""Tests for the processing pipeline."""

import asyncio

import pytest

from spawn_agent.core.pipeline import Pipeline


class TestPipeline:
    """Test multi-stage processing pipeline."""

    @pytest.mark.asyncio
    async def test_single_stage(self):
        results = []

        async def process(event):
            results.append(event["value"] * 2)
            return event

        pipeline = Pipeline("test")
        pipeline.add_stage("double", process)
        await pipeline.start()

        await pipeline.push({"value": 5})
        await asyncio.sleep(0.1)

        await pipeline.stop()
        assert results == [10]

    @pytest.mark.asyncio
    async def test_multi_stage(self):
        outputs = []

        async def stage1(event):
            event["value"] *= 2
            return event

        async def stage2(event):
            outputs.append(event["value"])
            return event

        pipeline = Pipeline("multi")
        pipeline.add_stage("double", stage1)
        pipeline.add_stage("collect", stage2)
        await pipeline.start()

        await pipeline.push({"value": 3})
        await asyncio.sleep(0.2)

        await pipeline.stop()
        assert outputs == [6]

    @pytest.mark.asyncio
    async def test_stage_filtering(self):
        outputs = []

        async def filter_even(event):
            if event["value"] % 2 == 0:
                return event
            return None  # Filtered out

        async def collect(event):
            outputs.append(event["value"])
            return event

        pipeline = Pipeline("filter")
        pipeline.add_stage("filter", filter_even)
        pipeline.add_stage("collect", collect)
        await pipeline.start()

        for v in [1, 2, 3, 4, 5]:
            await pipeline.push({"value": v})
        await asyncio.sleep(0.3)

        await pipeline.stop()
        assert sorted(outputs) == [2, 4]

    def test_stats(self):
        pipeline = Pipeline("stats")
        pipeline.add_stage("s1", lambda e: e)
        stats = pipeline.stats
        assert stats["name"] == "stats"
        assert stats["stages"] == 1
        assert stats["processed"] == 0

    @pytest.mark.asyncio
    async def test_push_before_start_raises(self):
        pipeline = Pipeline("unstarted")
        with pytest.raises(RuntimeError, match="not been started"):
            await pipeline.push({"value": 1})
