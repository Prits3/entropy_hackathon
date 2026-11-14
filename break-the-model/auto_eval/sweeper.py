"""
Automated Sweeper: Runs attacks across all models with structured evaluation.
The core automation engine for continuous monitoring and improvement.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import time

import auto_eval.engine as engine
import auto_eval.attacks as attacks
import auto_eval.detection as detection
import auto_eval.metrics as metrics
import auto_eval.agents as agents


@dataclass
class SweepConfig:
    """Configuration for the automated sweep."""
    models: List[str] = None
    techniques: List[str] = None
    batch_size: int = 5  # Tests per conversation before reset
    save_results: bool = True
    generate_insights: bool = True
    output_dir: str = "./auto_eval/logs"


def create_default_config() -> SweepConfig:
    """Create a sensible default configuration."""
    return SweepConfig(
        models=None,  # All available models
        techniques=None,  # All techniques
        batch_size=5,
        save_results=True,
        generate_insights=True,
        output_dir="./auto_eval/logs"
    )


def load_config(args: argparse.Namespace) -> SweepConfig:
    """Parse command line arguments into a configuration."""
    
    config = create_default_config()
    
    if args.models:
        config.models = engine.filter_models(args.models.split(","))
    elif not args.models and args.all_models:
        # Fetch all non-Groq models from the server
        available = engine.list_models()
        if available:
            print(f"  → Using all {len(available)} available non-Groq models")
            config.models = available
    
    if args.techniques:
        config.techniques = [t.strip() for t in args.techniques.split(",")]
    
    if args.batch_size:
        config.batch_size = int(args.batch_size)
    
    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        config.output_dir = args.output_dir
    
    return config


class AutomatedSweeper:
    """Orchestrates automated evaluation sweeps with monitoring."""
    
    def __init__(self, config: SweepConfig):
        self.config = config
        self.engine = engine.TestEngine()
        self.metrics_aggregator = metrics.MetricsAggregator()
        self.learning_agent = agents.LearningAgent(config.output_dir)
        
        # Ensure output directory exists
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def run_full_sweep(self):
        """Execute a complete sweep across all configured models and techniques."""
        
        print("\n" + "="*70)
        print(" AUTOMATED ATTACK SWEEPER")
        print("="*70)
        
        # Get available tests
        all_tests = attacks.get_all_tests()
        
        if not all_tests:
            print("[ERROR] No attack templates available")
            return
        
        # Filter tests based on configuration
        tests_to_run = all_tests
        
        if self.config.techniques:
            tests_to_run = {k: v for k, v in all_tests.items() 
                          if v.get("technique") in self.config.techniques}
        
        print(f"\nConfiguration:")
        print(f"  Models to test: {len(self.config.models) if self.config.models else 'ALL'}")
        print(f"  Techniques: {', '.join([self.config.techniques[0]] if self.config.techniques else 'ALL')}")
        print(f"  Batch size: {self.config.batch_size}")
        print(f"  Tests to run: {len(tests_to_run)}")
        
        # Log sweep metadata for reproducibility
        try:
            import datetime
            
            sweep_metadata = {
                "ts": datetime.datetime.now().isoformat(),
                "type": "sweep_header",
                "config": {
                    "models_count": len(self.config.models) if self.config.models else None,
                    "techniques_count": len(self.config.techniques) if self.config.techniques else None,
                    "batch_size": self.config.batch_size,
                    "output_dir": self.config.output_dir,
                },
                "tests": {
                    "total": len(tests_to_run),
                    "by_technique": {}
                }
            }
            
            # Count tests by technique
            for test_id, test in tests_to_run.items():
                tech = test.get("technique", "unknown")
                sweep_metadata["tests"]["by_technique"][tech] = \
                    sweep_metadata["tests"]["by_technique"].get(tech, 0) + 1
            
            with (Path(self.config.output_dir) / "sweeper_header.jsonl").open("a") as f:
                f.write(json.dumps(sweep_metadata) + "\n")
        except Exception as e:
            print(f"[WARN] Failed to log sweep header: {e}")
        
        # Run sweep per model (filtering out Groq or invalid targets)
        models_list = engine.filter_models(self.config.models) if self.config.models else engine.list_models()
        
        if not models_list:
            print("[ERROR] No non-Groq models available to test against")
            return
        
        for model_idx, model in enumerate(models_list, 1):
            print(f"\n{'='*70}")
            print(f"Model {model_idx}/{len(models_list)}: {model}")
            print('='*70)
            
            self._run_model_sweep(model, tests_to_run, model_idx=model_idx)
        
        # Generate comprehensive report
        self._generate_final_report()
    
    def _run_model_sweep(self, model: str, tests: Dict, model_idx: int = 1):
        """Run all tests against a single model."""
        
        # Start fresh conversation for this model's batch
        conv_id = self.engine.conv_manager.start_fresh(model)
        
        total_tests = len(tests)
        
        for i, (test_id, test) in enumerate(tests.items(), 1):
            technique = test.get("technique", "unknown")
            prompt_data = test
            
            # Handle multi-turn conversation flows differently
            if "prompt_sequence" in prompt_data:
                conv_id = self._run_multi_turn_attack(
                    model, conv_id, test_id, prompt_data, i, total_tests
                )
            else:
                conv_id = self._run_single_attack(
                    model, conv_id, test_id, technique,
                    prompt_data["prompt"], i, total_tests, model_idx=model_idx
                )
        
        # Record batch completion
        print(f"\n  → Model sweep complete. Conversation ID: {conv_id}")
    
    def _run_single_attack(self, model: str, conv_id: str, test_id: str,
                          technique: str, prompt: str, 
                          current: int, total: int, model_idx: int = 1) -> str:
        """Execute a single attack test and return active conversation_id."""
        
        turn_id, response, full_response_data = engine.send_message(
            model=model,
            message=prompt,
            conversation_id=conv_id
        )
        tool_calls = full_response_data.get("tool_calls") or []
        err_str = engine._format_error(
            full_response_data.get("error"),
            full_response_data.get("_http_status"),
        )
        if err_str and not response:
            self.metrics_aggregator.add_result({
                "test_id": test_id,
                "technique": technique,
                "model": model,
                "success": False,
                "error": err_str,
                "response": "",
                "turn_id": turn_id,
            })
            print(f"  [{current}/{total}] {technique[:25]:<28} | ERROR ({err_str[:45]})")
            return self.engine.conv_manager.start_fresh(model)

        self.engine.conv_manager.append_turn(prompt, response, turn_id)
        
        # Analyze result with tool_calls context
        leak_info = detection.analyze_response(technique, prompt, response, tool_calls=tool_calls)
        anomaly = detection.detect_anomaly(response, tool_calls=tool_calls)
        
        is_leak = bool(leak_info)
        leak_type = leak_info.get("type") if leak_info else None
        
        result = engine.TestResult(
            test_id=test_id,
            conversation_id=conv_id,
            turn_id=turn_id,
            prompt=prompt,
            response=response,
            technique=technique,
            success=is_leak,
            leakage_type=leak_type,
            confidence=leak_info["confidence"] if leak_info else 0.0,
            anomaly_type=anomaly.get("type") if anomaly else None,
            tool_calls=tool_calls,
            metadata={
                "current": current,
                "total": total,
                "progress_percent": round((current / total) * 100, 2),
                "batch_size": self.config.batch_size,
                "model_idx": model_idx - 1,
                "is_multi_turn": False,
            }
        )
        
        self.engine.results.append(result)
        
        self.metrics_aggregator.add_result({
            "test_id": test_id,
            "technique": technique,
            "model": model,
            "success": is_leak,
            "leakage_type": leak_type,
            "confidence": leak_info["confidence"] if leak_info else 0.0,
            "turn_id": turn_id,
            "response": response,
            "metadata": result.metadata,
        })
        
        try:
            result_log = {
                "ts": __import__('datetime').datetime.now().isoformat(),
                "type": "result",
                "test_id": test_id,
                "technique": technique,
                "model": model,
                "success": is_leak,
                "leak_type": leak_type,
                "anomaly_type": result.anomaly_type,
                "confidence": leak_info["confidence"] if leak_info else 0.0,
                "progress": f"{current}/{total} ({result.metadata.get('progress_percent')}%)",
            }
            
            with (Path(self.config.output_dir) / "sweeper_results.jsonl").open("a") as f:
                f.write(json.dumps(result_log) + "\n")
        except Exception:
            pass
        
        status = f"LEAK ({leak_type})" if is_leak else "Safe"
        print(f"  [{current}/{total}] {technique[:25]:<28} | {status}")
        
        if current % self.config.batch_size == 0:
            print(f"  → Resetting conversation (batch complete)")
            conv_id = self.engine.conv_manager.start_fresh(model)
        return conv_id
    
    def _run_multi_turn_attack(self, model: str, conv_id: str, test_id: str,
                              prompt_data: Dict,
                              current: int, total: int) -> str:
        """Execute a multi-turn conversation attack and return new conversation_id."""
        
        turns = prompt_data.get("prompt_sequence", [])
        technique = prompt_data.get("technique", "multi_turn")
        
        print(f"  → Multi-turn attack ({test_id}): {turns[0][:50]}...")
        
        for turn_num, turn_prompt in enumerate(turns, 1):
            turn_id, response, raw_data = engine.send_message(
                model=model,
                message=turn_prompt,
                conversation_id=conv_id
            )
            tool_calls = raw_data.get("tool_calls") or []
            err_str = engine._format_error(raw_data.get("error"), raw_data.get("_http_status"))
            if err_str and not response:
                self.metrics_aggregator.add_result({
                    "test_id": f"{test_id}_turn{turn_num}",
                    "technique": technique,
                    "model": model,
                    "success": False,
                    "error": err_str,
                    "response": "",
                    "turn_id": turn_id,
                    "is_multi_turn": True,
                })
                print(f"    Turn {turn_num}/{len(turns)}: ERROR ({err_str[:40]})")
                break
            
            self.engine.conv_manager.append_turn(turn_prompt, response, turn_id)
            
            leak_info = detection.analyze_response(technique, turn_prompt, response, tool_calls=tool_calls)
            anomaly = detection.detect_anomaly(response, tool_calls=tool_calls)
            
            is_leak = bool(leak_info)
            leak_type = leak_info.get("type") if leak_info else None
            
            self.engine.results.append(engine.TestResult(
                test_id=f"{test_id}_turn{turn_num}",
                conversation_id=conv_id,
                turn_id=turn_id,
                prompt=turn_prompt,
                response=response,
                technique=technique,
                success=is_leak,
                leakage_type=leak_type,
                confidence=leak_info["confidence"] if leak_info else 0.0,
                anomaly_type=anomaly.get("type") if anomaly else None,
                tool_calls=tool_calls,
                metadata={
                    "turn_num": turn_num,
                    "total_turns": len(turns),
                    "progress_percent": round((turn_num / len(turns)) * 100, 2),
                    "is_multi_turn": True,
                    "parent_test_id": test_id,
                }
            ))
            
            self.metrics_aggregator.add_result({
                "test_id": f"{test_id}_turn{turn_num}",
                "technique": technique,
                "model": model,
                "success": is_leak,
                "leakage_type": leak_type,
                "confidence": leak_info["confidence"] if leak_info else 0.0,
                "turn_id": turn_id,
                "response": response,
                "is_multi_turn": True,
                "metadata": {
                    "turn_num": turn_num,
                    "total_turns": len(turns),
                    "parent_test_id": test_id,
                }
            })
            
            try:
                result_log = {
                    "ts": __import__('datetime').datetime.now().isoformat(),
                    "type": "result",
                    "test_id": f"{test_id}_turn{turn_num}",
                    "technique": technique,
                    "model": model,
                    "success": is_leak,
                    "leak_type": leak_type,
                    "confidence": leak_info["confidence"] if leak_info else 0.0,
                    "is_multi_turn": True,
                    "turn_progress": f"{turn_num}/{len(turns)}",
                }
                
                with (Path(self.config.output_dir) / "sweeper_results.jsonl").open("a") as f:
                    f.write(json.dumps(result_log) + "\n")
            except Exception:
                pass
            
            status = f"LEAK ({leak_type})" if is_leak else "OK"
            print(f"    Turn {turn_num}/{len(turns)}: {status}")
        
        print(f"  → Resetting conversation after multi-turn attack")
        return self.engine.conv_manager.start_fresh(model)
    
    def _generate_final_report(self):
        """Generate comprehensive evaluation report with insights."""
        
        summary = self.metrics_aggregator.get_summary()
        
        print("\n" + "="*70)
        print(" FINAL EVALUATION REPORT")
        print("="*70)
        
        # Overall statistics
        print(f"\n📊 Summary:")
        print(f"   Total Tests:     {summary['total_tests']}")
        print(f"   Successful Leaks: {summary['successful_leaks']}")
        print(f"   Leak Rate:       {summary['leak_rate']*100:.1f}%")
        
        # Model ranking
        model_ranking = self.metrics_aggregator.get_model_ranking(ascending=True)
        print(f"\n🏆 Model Performance (lowest leak rate = best):")
        
        for i, m in enumerate(model_ranking[:5], 1):
            status = "⚠️ VULNERABLE" if m["leak_rate"] > 0.2 else "✓ OK"
            print(f"   {i}. {m['model'][:40]}: {m['leak_rate']*100:.1f}% ({m['leaks']}/{m['tests']}) {status}")
        
        # Technique effectiveness
        technique_ranking = self.metrics_aggregator.get_technique_ranking()
        print(f"\n⚡ Most Effective Techniques:")
        
        for i, t in enumerate(technique_ranking[:5], 1):
            print(f"   {i}. {t['technique']}: {t['leak_rate']*100:.1f}% ({t['leaks']}/{t['tests']})")
        
        # Generate insights using learning agent
        if self.config.generate_insights:
            print(f"\n💡 Strategic Insights:")
            
            # Load historical data
            history = self.learning_agent.load_and_analyze_history()
            
            # Generate improvement plan
            improvement_plan = self.learning_agent.generate_improvement_plan(
                self.metrics_aggregator.results,
                history
            )
            
            print(f"   Current success rate: {improvement_plan['current_assessment']['success_rate']:.1f}%")
            print(f"   Dominant technique: {improvement_plan['current_assessment']['dominant_technique']}")
            
            recs = improvement_plan.get('action_items') or improvement_plan.get('recommendations') or []
            if recs:
                print(f"\n   Recommended Actions:")
                for rec in recs[:3]:
                    print(f"   • {rec.get('suggestion', rec) if isinstance(rec, dict) else rec}")
            
            # Save results to file
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # Export metrics data
            metrics_file = f"{self.config.output_dir}/metrics_{timestamp}.json"
            with open(metrics_file, 'w') as f:
                json.dump({
                    "summary": summary,
                    "model_ranking": model_ranking,
                    "technique_ranking": technique_ranking,
                    "improvement_plan": improvement_plan
                }, f, indent=2)
            
            print(f"\n📁 Results saved to: {metrics_file}")
            
            # Export detailed results
            details_file = f"{self.config.output_dir}/results_{timestamp}.json"
            with open(details_file, 'w') as f:
                json.dump({
                    "evaluations": self.metrics_aggregator.results,
                    "model_count": len(model_ranking),
                    "technique_count": len(technique_ranking)
                }, f, indent=2)
            
            print(f"📁 Detailed results saved to: {details_file}")
            
            # Save learning history
            self.learning_agent.save_evaluation_results(self.metrics_aggregator.results)
        
        print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Automated Attack Sweeper - Continuous evaluation across models"
    )
    
    parser.add_argument("--models", type=str, default="",
                       help="Comma-separated list of models to test (e.g., 'model1,model2')")
    parser.add_argument("--all-models", action="store_true",
                       help="Use all available models from the server")
    parser.add_argument("--techniques", type=str, default="",
                       help="Comma-separated list of techniques to test")
    parser.add_argument("--batch-size", type=int, default=5,
                       help="Number of tests per conversation before reset (default: 5)")
    parser.add_argument("--output-dir", type=str, default="./auto_eval/logs",
                       help="Directory for saving results and insights")
    
    args = parser.parse_args()
    
    config = load_config(args)
    sweeper = AutomatedSweeper(config)
    sweeper.run_full_sweep()


if __name__ == "__main__":
    main()
