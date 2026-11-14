#!/usr/bin/env python3
"""
Scheduled Evaluation Runner: Designed for cron/systemd integration.
Provides structured output, error handling, and logging for automated scheduling.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import traceback

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import auto_eval.engine as engine
import auto_eval.attacks as attacks
import auto_eval.detection as detection
import auto_eval.metrics as metrics
import auto_eval.agents as agents


class CronRunner:
    """
    Evaluation runner optimized for scheduled/automated execution.
    
    Features:
    - Structured logging suitable for CI/CD pipelines
    - Comprehensive error handling with graceful degradation
    - Output in JSON format for easy parsing by schedulers
    - State persistence across runs
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or {
            "models": None,  # All models
            "techniques": None,  # All techniques
            "output_dir": "./auto_eval/logs",
            "interval_seconds": 3600,  # Default 1 hour between sweeps
            "max_retries": 3,
            "retry_delay": 5,
        }
        
        self.output_dir = Path(self.config["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # State files
        self.state_file = self.output_dir / ".cron_state.json"
        self.metrics_file = self.output_dir / "metrics_latest.json"
        
        # Initialize components
        self.engine = engine.TestEngine()
        self.learning_agent = agents.LearningAgent(str(self.output_dir))
        
        # Load previous state if exists
        self._load_state()
    
    def _load_state(self):
        """Load execution state from disk."""
        try:
            with open(self.state_file, 'r') as f:
                self.previous_run = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.previous_run = {
                "last_successful_timestamp": None,
                "last_techniques": [],
                "cumulative_tests": 0,
                "cumulative_leaks": 0,
            }
    
    def _save_state(self, run_info: Dict):
        """Save execution state for next run."""
        self.previous_run.update({
            "last_successful_timestamp": datetime.now().isoformat(),
            "last_techniques": [t.get("technique") for t in run_info.get("tests", [])],
            "cumulative_tests": self.previous_run.get("cumulative_tests", 0) + 
                               sum(1 for r in run_info.get("results", []) if isinstance(r, dict)),
            "cumulative_leaks": self.previous_run.get("cumulative_leaks", 0) + 
                               sum(1 for r in run_info.get("results", []) if isinstance(r, dict) and r.get("success")),
        })
        
        with open(self.state_file, 'w') as f:
            json.dump(self.previous_run, f, indent=2)
    
    def run_sweep(self) -> Dict:
        """
        Execute a single evaluation sweep.
        
        Returns structured result suitable for JSON output in cron jobs.
        """
        start_time = time.time()
        
        # Get all available tests
        all_tests = attacks.get_all_tests()
        
        if not all_tests:
            return {
                "status": "error",
                "message": "No attack templates available",
                "duration_seconds": 0,
            }
        
        # Filter tests based on configuration
        tests_to_run = list(all_tests.items())
        
        if self.config.get("techniques"):
            tests_to_run = [(k, v) for k, v in tests_to_run 
                          if v.get("technique") in self.config["techniques"]]
        
        # Get non-Groq models to test against
        if self.config.get("models"):
            models_list = engine.filter_models(self.config["models"].split(","))
        else:
            models_list = engine.list_models()
        
        if not models_list:
            return {
                "status": "error",
                "message": "No models available to test against",
                "duration_seconds": 0,
            }
        
        # Execute sweep
        results = []
        model_stats = {}
        technique_stats = {}
        
        for model_idx, model in enumerate(models_list, 1):
            try:
                conv_id = self.engine.conv_manager.start_fresh(model)
                
                # Run tests against this model
                for test_id, test in tests_to_run:
                    technique = test.get("technique", "unknown")
                    prompt_data = test
                    
                    if "prompt_sequence" in prompt_data:
                        success, leak_type, err_str, resp_txt = self._run_multi_turn(
                            model, conv_id, prompt_data, test_id
                        )
                    else:
                        success, leak_type, err_str, resp_txt = self._run_single_attack(
                            model, conv_id, technique,
                            prompt_data["prompt"], test_id
                        )

                    results.append({
                        "test_id": test_id,
                        "technique": technique,
                        "model": model,
                        "success": success,
                        "leakage_type": leak_type,
                        "error": err_str,
                        "response": resp_txt,
                        "timestamp": datetime.now().isoformat(),
                    })
                
                # Reset conversation for next model
                conv_id = self.engine.conv_manager.start_fresh(model)
                
            except Exception as e:
                # Log error but continue with other models
                print(f"[ERROR] Model {model} failed: {str(e)}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
        
        valid_results = [r for r in results if not (r.get("error") and not r.get("response"))]
        total_tests = len(valid_results)
        successful_leaks = sum(1 for r in valid_results if r.get("success"))
        leak_rate = (successful_leaks / total_tests * 100) if total_tests > 0 else 0
        
        duration = time.time() - start_time
        
        # Update aggregators and save metrics
        aggregator = metrics.MetricsAggregator()
        for r in results:
            aggregator.add_result(r)
        
        # Generate insights
        if successful_leaks > 0:
            improvements = self.learning_agent.synthesize_new_technique(
                results, 
                ["L1_DIRECT", "L2_ROLEPLAY"]
            )
        else:
            improvements = {"error": "No successful attacks to analyze"}
        
        # Save this run's metrics
        metrics_file = self.output_dir / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(metrics_file, 'w') as f:
            json.dump({
                "summary": aggregator.get_summary(),
                "model_ranking": aggregator.get_model_ranking(ascending=True),
                "technique_ranking": aggregator.get_technique_ranking(),
                "improvements": improvements,
                "run_info": {
                    "start_time": datetime.now().isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "duration_seconds": duration,
                    "models_tested": models_list,
                    "techniques_tested": [t.get("technique") for t in tests_to_run],
                }
            }, f, indent=2)
        
        # Update latest metrics file (atomic rename)
        self.metrics_file.write_text(metrics_file.read_text())
        
        # Save state
        self._save_state({
            "results": results,
            "tests": tests_to_run,
        })
        
        return {
            "status": "success",
            "summary": aggregator.get_summary(),
            "model_ranking": [m for m in aggregator.get_model_ranking(ascending=True)[:5]],
            "technique_ranking": [t for t in aggregator.get_technique_ranking()[:5]],
            "improvements": improvements,
            "metrics_file": str(metrics_file),
            "duration_seconds": duration,
            "tests_run": total_tests,
            "successful_leaks": successful_leaks,
            "leak_rate": round(leak_rate, 2),
        }
    
    def _run_single_attack(self, model: str, conv_id: str, 
                          technique: str, prompt: str, test_id: str) -> tuple:
        """Execute a single attack and return (success, leak_type, error, response)."""
        
        turn_id, response, raw_data = engine.send_message(
            model=model,
            message=prompt,
            conversation_id=conv_id
        )
        err_str = engine._format_error(raw_data.get("error"), raw_data.get("_http_status"))
        if err_str and not response:
            return False, None, err_str, ""

        self.engine.conv_manager.append_turn(prompt, response, turn_id)
        tool_calls = raw_data.get("tool_calls") or []
        leak_info = detection.analyze_response(technique, prompt, response, tool_calls=tool_calls)
        
        success = bool(leak_info)
        leak_type = leak_info.get("type") if leak_info else None
        
        return success, leak_type, None, response
    
    def _run_multi_turn(self, model: str, conv_id: str, 
                       prompt_data: Dict, test_id: str) -> tuple:
        """Execute a multi-turn attack and return (success, leak_type, error, response)."""
        
        turns = prompt_data.get("prompt_sequence", [])
        all_leaks = []
        last_err = None
        last_resp = ""
        
        for turn_num, turn_prompt in enumerate(turns, 1):
            turn_id, response, raw_data = engine.send_message(
                model=model,
                message=turn_prompt,
                conversation_id=conv_id
            )
            err_str = engine._format_error(raw_data.get("error"), raw_data.get("_http_status"))
            if err_str and not response:
                last_err = err_str
                break

            last_resp = response
            self.engine.conv_manager.append_turn(turn_prompt, response, turn_id)
            tool_calls = raw_data.get("tool_calls") or []
            leak_info = detection.analyze_response(
                prompt_data.get("technique", "multi_turn"), 
                turn_prompt, 
                response,
                tool_calls=tool_calls,
            )
            
            if leak_info:
                all_leaks.append({
                    "turn": turn_num,
                    "type": leak_info.get("type"),
                    "confidence": leak_info.get("confidence")
                })
        
        success = len(all_leaks) > 0
        leak_type = all_leaks[-1].get("type") if all_leaks else None
        
        return success, leak_type, (last_err if not last_resp else None), last_resp
    
    def get_status(self) -> Dict:
        """Get current execution status and statistics."""
        
        try:
            with open(self.metrics_file, 'r') as f:
                latest_metrics = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "status": "no_data",
                "message": "No evaluation data found yet"
            }
        
        summary = latest_metrics.get("summary", {})
        
        return {
            "status": "running",
            "latest_run": {
                "timestamp": datetime.now().isoformat(),
                "total_tests": summary.get("total_tests", 0),
                "successful_leaks": summary.get("successful_leaks", 0),
                "leak_rate": summary.get("leak_rate", 0),
            },
            "model_count": len(latest_metrics.get("model_ranking", [])),
            "technique_count": len(latest_metrics.get("technique_ranking", [])),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Scheduled evaluation runner for cron/systemd"
    )
    
    parser.add_argument("--action", choices=["sweep", "status"],
                       default="sweep",
                       help="Action to perform (default: sweep)")
    parser.add_argument("--models", type=str, default="",
                       help="Comma-separated list of models")
    parser.add_argument("--techniques", type=str, default="",
                       help="Comma-separated list of techniques")
    parser.add_argument("--output-dir", type=str, 
                       default="./auto_eval/logs",
                       help="Output directory for results")
    
    args = parser.parse_args()
    
    # Load configuration from arguments or defaults
    config = {
        "models": args.models if args.models else None,
        "techniques": args.techniques if args.techniques else None,
        "output_dir": args.output_dir,
    }
    
    runner = CronRunner(config)
    
    if args.action == "sweep":
        try:
            result = runner.run_sweep()
            
            # Output in structured format for cron parsing
            print(json.dumps({
                "event": "evaluation_complete",
                "result": result,
            }))
            
        except Exception as e:
            print(json.dumps({
                "event": "evaluation_error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }), file=sys.stderr)
            sys.exit(1)
    
    elif args.action == "status":
        status = runner.get_status()
        print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
