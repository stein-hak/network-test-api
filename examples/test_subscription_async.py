#!/usr/bin/env python3
"""
Example: Test subscription links in parallel using async client
"""

import asyncio
import sys
sys.path.insert(0, '..')

from network_test_client import AsyncNetworkTestClient


async def main():
    subscription_url = "https://gorillaerror.com/sub/stein"
    orchestrator_url = "http://10.11.0.3:8000"

    async with AsyncNetworkTestClient(orchestrator_url) as client:
        print("=== Testing Subscription Links (Parallel) ===\n")

        # Test first 5 links with 3 concurrent workers
        results = await client.test_subscription_links_parallel(
            subscription_url=subscription_url,
            max_links=5,
            timeout=25,
            max_concurrent=3
        )

        # Summary
        total = len(results)
        successful = sum(1 for r in results if 'result' in r and r['result'].get('successful', 0) > 0)

        print(f"\n=== Summary ===")
        print(f"Total links tested: {total}")
        print(f"Links with at least one success: {successful}")

        # Detailed results
        print(f"\n=== Detailed Results ===")
        for result in results:
            if 'error' in result:
                print(f"\n[{result['link_index']}] ❌ ERROR")
                print(f"   Error: {result['error']}")
            else:
                r = result['result']
                print(f"\n[{result['link_index']}] Workers: {r['successful']}/{r['total_workers']} successful")
                for worker_result in r.get('results', []):
                    worker_name = worker_result['worker_url'].split(':')[-2].split('.')[-1]
                    if worker_result.get('success'):
                        test = worker_result.get('test_result', {})
                        if test.get('success'):
                            print(f"   ✅ {worker_name}: {test.get('latency_ms', 0):.0f}ms")
                        else:
                            print(f"   ❌ {worker_name}: {test.get('error', 'failed')}")
                    else:
                        print(f"   ❌ {worker_name}: timeout")


if __name__ == "__main__":
    asyncio.run(main())
