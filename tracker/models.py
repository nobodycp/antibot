from django.db import models


class BlockedSubnet(models.Model):
    cidr = models.CharField(max_length=43, unique=True)  # مثال: 192.168.1.0/24

    class Meta:
        verbose_name_plural = "1.1 - Subnets"

    def __str__(self):
        return self.cidr

class BlockedIP(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    class Meta:
        verbose_name_plural = "1 - IP"
    def __str__(self):
        return self.ip_address

class BlockedISP(models.Model):
    isp = models.CharField(max_length=255, unique=True)
    class Meta:
        verbose_name_plural = "2 - ISP"
    def __str__(self):
        return self.isp

class BlockedBrowser(models.Model):
    browser = models.CharField(max_length=100, unique=True)
    class Meta:
        verbose_name_plural = "4 - Browser"
    def __str__(self):
        return self.browser

class BlockedOS(models.Model):
    os = models.CharField(max_length=100, unique=True)
    class Meta:
        verbose_name_plural = "3 - OS"
    def __str__(self):
        return self.os

class BlockedHostname(models.Model):
    hostname = models.CharField(max_length=255, unique=True)
    class Meta:
        verbose_name_plural = "5 - Hostname"
    def __str__(self):
        return self.hostname

class AllowedCountry(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    class Meta:
        verbose_name_plural = "7 - Allowed Country Codes"
    def __str__(self):
        return self.code.upper()

class Visitor(models.Model):
    ip_address = models.GenericIPAddressField()
    b_subnet = models.CharField(max_length=64, blank=True, default="")
    hostname = models.CharField(max_length=255, blank=True, null=True)
    isp = models.CharField(max_length=255, blank=True, null=True)
    os = models.CharField(max_length=100)
    browser = models.CharField(max_length=100)
    user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    country = models.CharField(max_length=100, blank=True, null=True)  # ✅ الحقل الجديد

    class Meta:
        verbose_name_plural = "Logs"
    def __str__(self):
        return f'{self.ip_address} - {self.timestamp}'

class RejectedVisitor(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    b_subnet = models.CharField(max_length=64, blank=True, default="")
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    isp = models.CharField(max_length=255, blank=True)
    hostname = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=100, blank=True)
    class Meta:
        verbose_name_plural = "Deny Logs"
    def __str__(self):
        return f"{self.ip_address} - {self.reason}"

class IPLog(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    count = models.PositiveIntegerField(default=1)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ip_address} ({self.count})"

