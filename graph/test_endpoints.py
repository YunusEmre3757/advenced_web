#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test of all LangGraph endpoints without starting servers.

This tests the graph logic directly without FastAPI/network overhead.
Useful for CI/CD and quick validation before sunumu (presentation).
"""

import asyncio
import sys
import os
from datetime import datetime

# Fix Windows encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# Add src to path
sys.path.insert(0, "src")

from seismic_graph.graphs.building_risk_graph import get_building_risk_graph
from seismic_graph.graphs.chat_graph import reset_chat_graph, get_chat_graph
from seismic_graph.checkpoint import setup_checkpointer, close_checkpointer
from seismic_graph.config import DRY_RUN, GROQ_API_KEY


async def test_building_risk_graph():
    """Test building risk graph with sample building data."""
    print("\n" + "="*60)
    print("[BUILDING RISK GRAPH TEST]")
    print("="*60)

    graph = get_building_risk_graph()

    # Test case 1: Low risk
    print("\n[Test 1] Low-risk building (new, reinforced concrete, good soil)")
    result1 = await graph.ainvoke({
        "building": {
            "constructionYear": 2020,
            "floorCount": 3,
            "structuralSystem": "reinforced_concrete",
            "soilType": "ZA",
            "columnCracks": False,
            "pastDamage": False,
            "softStorey": False,
            "heavyTopFloor": False,
            "irregularShape": False,
            "retrofitDone": False,
        },
        "location": {
            "latitude": 41.0082,
            "longitude": 28.9784,
            "label": "Istanbul",
            "source": "address",
        },
    })

    print(f"  Score: {result1.get('totalScore')}/100")
    print(f"  Level: {result1.get('level')} ({result1.get('label')})")
    print(f"  Confidence: {result1.get('confidence')}")
    print(f"  Summary: {result1.get('summary')[:100]}...")

    # Test case 2: High risk
    print("\n[Test 2] High-risk building (pre-2000, masonry, soft story, near fault)")
    result2 = await graph.ainvoke({
        "building": {
            "constructionYear": 1995,
            "floorCount": 6,
            "structuralSystem": "masonry",
            "soilType": "ZE",
            "columnCracks": True,
            "pastDamage": True,
            "softStorey": True,
            "heavyTopFloor": True,
            "irregularShape": True,
            "retrofitDone": False,
        },
        "location": {
            "latitude": 39.8581,
            "longitude": 30.7935,
            "label": "Ankara (sample)",
            "source": "address",
        },
    })

    print(f"  Score: {result2.get('totalScore')}/100")
    print(f"  Level: {result2.get('level')} ({result2.get('label')})")
    print(f"  Confidence: {result2.get('confidence')}")
    print(f"  Drivers: {result2.get('buildingDrivers')}")

    return result1, result2


async def test_chat_graph():
    """Test chat graph with stateful conversation."""
    print("\n" + "="*60)
    print("[CHAT GRAPH TEST - Stateful]")
    print("="*60)

    checkpointer = await setup_checkpointer()
    reset_chat_graph()
    graph = get_chat_graph(checkpointer)

    print("\n[Test 1] Simple earthquake question")
    result = await graph.ainvoke(
        {
            "question": "Istanbul'da 5.0 büyüklüğünde deprem olursa ne olur?",
            "user_context": {"latitude": 41.0082, "longitude": 28.9784},
        },
        config={"configurable": {"thread_id": "test_session_1"}},
    )
    print(f"  Category: {result.get('category')}")
    print(f"  Answer: {result.get('answer')[:100]}...")

    print("\n[Test 2] Follow-up question (same session)")
    result2 = await graph.ainvoke(
        {"question": "Ne tür yardım yapmalıyız?", "user_context": {}},
        config={"configurable": {"thread_id": "test_session_1"}},
    )
    print(f"  Category: {result2.get('category')}")
    print(f"  Answer (using prior context): {result2.get('answer')[:100]}...")

    await close_checkpointer()
    return result, result2


async def main():
    """Run all graph tests."""
    print("\n" + "[LANGGRAPH ENDPOINT TESTS]".center(60))
    print(f"DRY_RUN: {DRY_RUN} (LLM calls {'DISABLED' if DRY_RUN else 'ENABLED'})")
    print(f"GROQ_API_KEY: {'SET' if GROQ_API_KEY else 'NOT SET (will use fallback)'}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    try:
        # Test building risk graph
        br1, br2 = await test_building_risk_graph()

        # Test chat graph
        ch1, ch2 = await test_chat_graph()

        # Summary
        print("\n" + "="*60)
        print("[SUCCESS] ALL TESTS PASSED")
        print("="*60)
        print("\nGraphs tested:")
        print("  [OK] building_risk_graph (deterministic scoring + LLM + evaluator)")
        print("  [OK] chat_graph (stateful multi-turn conversation)")
        print("\nRemaining graphs (untested here, but implemented):")
        print("  [-] notify_graph (severity routing)")
        print("  [-] quake_detail_graph (multi-source enrichment)")
        print("  [-] safe_check_graph (family safety assessment)")
        print("\nTo test all graphs with FastAPI:")
        print("  cd graph && uvicorn seismic_graph.api:app --port 8002 --reload")
        print("  Then visit: http://localhost:8002/docs")

    except Exception as e:
        print(f"\n[ERROR] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
