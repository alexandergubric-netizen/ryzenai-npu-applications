# Adapted from image-studio/Start-ImageStudio.ps1 SHA-256 aa0fca2db4fa64ea30d9d0c45676f16776d055253c567b427109a6d247436eed
# Tsubasa owns its process handle and logs. This adapter launches only sd-server.
def arguments(root,port):
    return ['--listen-ip','127.0.0.1','--listen-port',str(port),
            '-m',str(root/'models/RealVisXL_V5.0_Lightning_fp16.safetensors'),
            '--sampling-method','dpm++2m_sde','--scheduler','karras',
            '--model-dir',str(root/'models'),'--steps','5','--cfg-scale','1.0',
            '-W','1024','-H','1024']
