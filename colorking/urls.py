"""
URL configuration for colorking project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from sales.views import print_nota, get_product_price, get_customer_tempo
from sales import views

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/', admin.site.urls),
    path('print-nota/<str:nomor_faktur>/', print_nota, name='print_nota'), # <-- Add this line
    path('api/get-price/<str:kode_barang>/', get_product_price, name='get_product_price'),
    path('api/get-tempo/<str:kode_cust>/', get_customer_tempo, name='get_customer_tempo'),
    path('product/<str:kode_barang>/', views.product_detail, name='product_detail'),
    path('restock/new/', views.create_restock, name='create_restock'),
    path('stock/delete/<int:tx_id>/', views.delete_stock_transaction, name='delete_stock_transaction'),
    path('print-surat-jalan/<str:nomor_faktur>/', views.print_surat_jalan, name='print_surat_jalan'),
    path('readymix/new/', views.create_readymix, name='create_readymix'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('api/dashboard-data/', views.dashboard_data_api, name='dashboard_data_api'),
]
