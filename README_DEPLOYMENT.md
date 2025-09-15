# ComfyUI Production Deployment

This is a production-ready deployment of ComfyUI with dual GPU support, load balancing, and automatic service management.

## 🚀 Features

- **Dual GPU Support**: Runs on CUDA devices 0 and 1 simultaneously
- **Auto-restart Watchdog**: Automatically restarts services if they crash
- **SystemD Integration**: Services start automatically on system boot
- **Load Balancing**: Smart load balancer for distributing workload
- **Web Interface**: Selector interface for choosing GPU instances
- **Production Logs**: Comprehensive logging system

## 📁 Project Structure

```
├── comfy_watchdog.sh           # Main watchdog script for auto-restart
├── comfyui-watchdog.service    # SystemD service configuration
├── comfyui_load_balancer.py    # Load balancer for dual GPU setup
├── smart_load_balancer.py      # Smart load balancer with queue management
├── comfyui_selector.html       # Web interface for GPU selection
├── simple_proxy.py             # Simple proxy server
├── main.py                     # Main ComfyUI application
└── ... (other ComfyUI files)
```

## 🔧 Installation & Setup

### 1. Prerequisites
- Ubuntu/Linux system
- NVIDIA GPUs (CUDA support)
- Miniconda/Anaconda
- Python 3.10+

### 2. Environment Setup
```bash
# Create conda environment
conda create -n latentsync python=3.10
conda activate latentsync

# Install dependencies
pip install -r requirements.txt
```

### 3. SystemD Service Setup
```bash
# Copy service file to system directory
sudo cp comfyui-watchdog.service /etc/systemd/system/

# Enable and start service
sudo systemctl enable comfyui-watchdog
sudo systemctl start comfyui-watchdog

# Check status
sudo systemctl status comfyui-watchdog
```

## 🌐 Service URLs

- **GPU 0**: http://89.208.11.177:8188
- **GPU 1**: http://89.208.11.177:8189
- **Load Balancer**: Available through various balancer scripts
- **Web Selector**: Available via comfyui_selector.html

## 🛠 Management Commands

```bash
# Check service status
sudo systemctl status comfyui-watchdog

# Restart services
sudo systemctl restart comfyui-watchdog

# View logs
sudo journalctl -u comfyui-watchdog -f

# Manual watchdog run
./comfy_watchdog.sh
```

## 📊 Monitoring

- **Watchdog Logs**: `/home/epycmax/comfy_logs/watchdog.log`
- **GPU 0 Logs**: `/home/epycmax/comfy_logs/comfy_gpu0.log`
- **GPU 1 Logs**: `/home/epycmax/comfy_logs/comfy_gpu1.log`
- **System Logs**: `sudo journalctl -u comfyui-watchdog`

## 🔧 Configuration Files

### Watchdog Configuration
The watchdog script (`comfy_watchdog.sh`) monitors and restarts ComfyUI instances:
- Checks every 30 seconds
- Automatically restarts crashed processes
- Manages PID files
- Comprehensive logging

### SystemD Service
The service (`comfyui-watchdog.service`) ensures:
- Auto-start on system boot
- Automatic restart on failure
- Proper environment variables
- User-space execution

## 🚨 Troubleshooting

### Services Not Starting
```bash
# Check service status
sudo systemctl status comfyui-watchdog

# Check logs
sudo journalctl -u comfyui-watchdog --no-pager

# Manual start for debugging
./comfy_watchdog.sh
```

### GPU Issues
```bash
# Check GPU status
nvidia-smi

# Check CUDA availability
python -c "import torch; print(torch.cuda.is_available())"
```

### Network Issues
```bash
# Check port availability
netstat -tulpn | grep -E "(8188|8189)"

# Test local connection
curl http://localhost:8188
curl http://localhost:8189
```

## 📝 License

This deployment extends ComfyUI with production features. Original ComfyUI license applies.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📞 Support

For deployment issues or questions, please create an issue in this repository.
