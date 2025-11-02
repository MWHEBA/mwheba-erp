"""
Custom Email Backend لتجاهل مشاكل SSL Certificate
"""
import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend


class SSLEmailBackend(SMTPBackend):
    """Email backend يتجاهل مشاكل SSL Certificate"""
    
    def open(self):
        if self.connection:
            return False
        
        connection_params = {}
        if self.timeout is not None:
            connection_params['timeout'] = self.timeout
        if self.use_ssl:
            connection_params['context'] = ssl._create_unverified_context()
        
        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )
            
            # تفعيل TLS مع تعطيل التحقق
            if self.use_tls:
                self.connection.ehlo()
                self.connection.starttls(context=ssl._create_unverified_context())
                self.connection.ehlo()
            
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            
            return True
        except Exception:
            if not self.fail_silently:
                raise
