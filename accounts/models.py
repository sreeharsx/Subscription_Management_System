from django.db import models
from django.contrib.auth.models import User


class CustomerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    company_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.company_name})"

    class Meta:
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"
        ordering = ['-created_at']
