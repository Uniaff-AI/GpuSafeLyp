async def check_task_completion(server_url: str, task_id: str, prompt_id: str):
    """Проверяет завершение задачи используя ComfyUI History API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Get task history from ComfyUI
            async with session.get(f"http://{server_url}/history/{prompt_id}",
                                 timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    history_data = await response.json()
                    
                    if prompt_id in history_data:
                        task_data = history_data[prompt_id]
                        status = task_data.get("status", {})
                        
                        # Check if task completed successfully
                        if status.get("status_str") == "success" and status.get("completed"):
                            outputs = task_data.get("outputs", {})
                            
                            # Find the output video file
                            result_file = None
                            for node_id, node_outputs in outputs.items():
                                if "gifs" in node_outputs:
                                    for gif_info in node_outputs["gifs"]:
                                        if gif_info.get("format") == "video/h264-mp4":
                                            result_file = Path(gif_info["fullpath"])
                                            break
                                if result_file:
                                    break
                            
                            if result_file and result_file.exists():
                                log_with_time(f"✅ Task {task_id[:8]} completed successfully: {result_file}")
                                
                                # Update task status
                                if task_id in tasks:
                                    tasks[task_id]["status"] = "completed"
                                    tasks[task_id]["progress"] = 100
                                    tasks[task_id]["result_url"] = f"http://89.208.11.177:8000/download/{result_file.name}"
                                    tasks[task_id]["message"] = f"✅ Completed successfully!"
                                    
                                    end_time = datetime.now()
                                    start_time = datetime.fromisoformat(tasks[task_id]["started_at"].replace('Z', '+00:00'))
                                    duration = format_duration(start_time, end_time)
                                    tasks[task_id]["completed_at"] = end_time.isoformat() + "Z"
                                    tasks[task_id]["duration"] = duration
                                
                                return {"success": True, "result_file": str(result_file)}
                            else:
                                log_with_time(f"❌ Task {task_id[:8]} completed but no result file found")
                                
                        elif status.get("status_str") == "error":
                            log_with_time(f"❌ Task {task_id[:8]} failed with error in ComfyUI")
                            if task_id in tasks:
                                tasks[task_id]["status"] = "failed"
                                tasks[task_id]["message"] = "❌ ComfyUI processing error"
                            return {"success": False, "error": "ComfyUI processing error"}
                    
                    # Task not found in history - still running or lost
                    return {"success": False, "error": "Task not found in history"}
                else:
                    log_with_time(f"❌ Failed to get history from {server_url}: {response.status}")
                    return {"success": False, "error": f"History API error: {response.status}"}
                    
    except Exception as e:
        log_with_time(f"❌ Error checking task completion: {e}")
        return {"success": False, "error": str(e)}
    
    # Fallback to old file search method if API fails
    log_with_time(f"📁 Falling back to file search for task {task_id[:8]}")
    try:
        output_dirs = [
            Path("ComfyUI-Production/output"),
            Path("ComfyUI/output"), 
            Path("ComfyUI/ComfyUI_main/output")
        ]
        
        result_file = None
        for output_dir in output_dirs:
            if output_dir.exists():
                pattern = "lipsync_result_*.mp4"
                files = list(output_dir.glob(pattern))
                
                if files:
                    # Get the most recent file
                    result_file = max(files, key=lambda x: x.stat().st_mtime)
                    break
        
        if result_file:
            log_with_time(f"✅ Task {task_id[:8]} found result via file search: {result_file}")
            
            if task_id in tasks:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["progress"] = 100
                tasks[task_id]["result_url"] = f"http://89.208.11.177:8000/download/{result_file.name}"
                tasks[task_id]["message"] = f"✅ Completed successfully!"
                
                end_time = datetime.now()
                start_time = datetime.fromisoformat(tasks[task_id]["started_at"].replace('Z', '+00:00'))
                duration = format_duration(start_time, end_time)
                tasks[task_id]["completed_at"] = end_time.isoformat() + "Z"
                tasks[task_id]["duration"] = duration
            
            return {"success": True, "result_file": str(result_file)}
        else:
            log_with_time(f"❌ Task {task_id[:8]} failed - no result file found")
            
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["message"] = "❌ No result file generated"
            
            return {"success": False, "error": "No result file found"}
            
    except Exception as e:
        log_with_time(f"❌ Fallback file search failed: {e}")
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["message"] = "❌ Error during result checking"
        return {"success": False, "error": str(e)}
