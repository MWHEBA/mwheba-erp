# -*- coding: utf-8 -*-
from django.urls import path
from cheques import views

app_name = 'cheques'

urlpatterns = [
    # 1. أوراق القبض (الشيكات الواردة)
    path('receivables/', views.ChequeReceivableListView.as_view(), name='receivable_list'),
    path('receivables/create/', views.ChequeReceivableCreateView.as_view(), name='receivable_create'),
    path('receivables/<int:pk>/', views.ChequeReceivableDetailView.as_view(), name='receivable_detail'),

    # 2. أوراق الدفع (الشيكات الصادرة)
    path('payables/', views.ChequePayableListView.as_view(), name='payable_list'),
    path('payables/create/', views.ChequePayableCreateView.as_view(), name='payable_create'),
    path('payables/<int:pk>/', views.ChequePayableDetailView.as_view(), name='payable_detail'),

    # 3. مسارات الحركات والعمليات السريعة (Action Endpoints)
    path('actions/<int:pk>/receive/', views.cheque_receive_action, name='cheque_receive_action'),
    path('actions/<int:pk>/issue/', views.cheque_issue_action, name='cheque_issue_action'),
    path('actions/<int:pk>/deposit/', views.cheque_deposit_action, name='cheque_deposit_action'),
    path('actions/<int:pk>/collect/', views.cheque_collect_action, name='cheque_collect_action'),
    path('actions/<int:pk>/bounce/', views.cheque_bounce_action, name='cheque_bounce_action'),
    path('actions/<int:pk>/endorse/', views.cheque_endorse_action, name='cheque_endorse_action'),
    path('actions/<int:pk>/clear/', views.cheque_clear_action, name='cheque_clear_action'),
    path('actions/<int:pk>/cancel/', views.cheque_cancel_action, name='cheque_cancel_action'),
    path('actions/<int:pk>/reverse/', views.cheque_reverse_action, name='cheque_reverse_action'),
    path('actions/<int:pk>/convert-guarantee/', views.cheque_convert_guarantee_action, name='cheque_convert_guarantee_action'),
    path('actions/<int:pk>/return-to-drawer/', views.cheque_return_to_drawer_action, name='cheque_return_to_drawer_action'),
    path('actions/<int:pk>/allocate-invoice/', views.cheque_allocate_invoice_action, name='cheque_allocate_invoice_action'),
    path('actions/<int:pk>/deallocate-invoice/<int:allocation_id>/', views.cheque_deallocate_invoice_action, name='cheque_deallocate_invoice_action'),


    # 4. حافظات الإيداع البنكية المجمعة
    path('batches/', views.ChequeBatchDepositListView.as_view(), name='batch_deposit_list'),
    path('batches/create/', views.ChequeBatchDepositCreateView.as_view(), name='batch_deposit_create'),
    path('batches/<int:pk>/', views.ChequeBatchDepositDetailView.as_view(), name='batch_deposit_detail'),

    # 5. دفاتر الشيكات البنكية واستبدال الأوراق التالفة
    path('checkbooks/', views.CheckbookListView.as_view(), name='checkbook_list'),
    path('checkbooks/create/', views.CheckbookCreateView.as_view(), name='checkbook_create'),
    path('checkbooks/<int:pk>/', views.CheckbookDetailView.as_view(), name='checkbook_detail'),
    path('checkbooks/leaf/<int:pk>/replace-ruined/', views.CheckbookRuinedLeafView.as_view(), name='checkbook_ruined_leaf'),

    # 6. طباعة الشيكات ومعايرة أبعاد دفاتر البنوك
    path('print/<int:pk>/', views.ChequePrintView.as_view(), name='cheque_print'),
    path('layouts/', views.BankChequeLayoutListView.as_view(), name='layout_list'),
    path('layouts/create/', views.BankChequeLayoutCreateView.as_view(), name='layout_create'),
    path('layouts/<int:pk>/edit/', views.BankChequeLayoutUpdateView.as_view(), name='layout_edit'),

    # 7. تقارير الشيكات ومطابقة الأستاذ المساعد وميزان الأعمار
    path('reports/subledger-reconciliation/', views.ChequeSubledgerReconciliationReportView.as_view(), name='subledger_reconciliation'),
    path('reports/aging/', views.ChequeAgingReportView.as_view(), name='cheque_aging'),
    path('reports/upcoming-due/', views.ChequeUpcomingDueReportView.as_view(), name='upcoming_due'),
]
