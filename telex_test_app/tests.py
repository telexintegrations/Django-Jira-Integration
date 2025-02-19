import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import requests
from django.test import RequestFactory
from django.conf import settings
from rest_framework.test import APITestCase
from rest_framework import status

# Assume your view is in app_name.views
from telex_test_app.views import JiraReportAPIView


class TestJiraReportAPIView(APITestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = JiraReportAPIView.as_view()
        self.request = self.factory.get('jira-report/')

        # Mock data
        self.mock_issues = {
            "pending": [
                {"fields": {"priority": {"name": "High"}}},
                {"fields": {"priority": {"name": "High"}}},
                {"fields": {"priority": {"name": "Medium"}}}
            ],
            "resolved": [
                {"fields": {"priority": {"name": "Low"}}},
                {"fields": {"priority": {"name": "Medium"}}}
            ]
        }

    @patch('telex_test_app.views.JiraReports')
    def test_successful_report_generation(self, MockJiraReports):
        # Configure mock
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.return_value = self.mock_issues
        mock_jira_instance.format_priority_counts.return_value = {"High": 2, "Medium": 1}
        mock_jira_instance.calculate_resolution_rate.return_value = "40%"
        mock_jira_instance.calculate_workload_index.return_value = "Moderate"

        # Execute view
        response = self.view(self.request)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overview']['new_unresolved_issues'], 3)
        self.assertEqual(response.data['overview']['resolved_issues'], 2)
        self.assertEqual(response.data['overview']['total_issues'], 5)
        self.assertIn('date_range', response.data)
        self.assertIn('priority_breakdown', response.data)
        self.assertIn('metrics', response.data)

        # Verify the mock was called with correct params
        MockJiraReports.assert_called_once_with(
            domain=settings.JIRA_DOMAIN,
            email=settings.JIRA_EMAIL,
            api_token=settings.JIRA_API_TOKEN
        )
        mock_jira_instance.get_weekly_issues.assert_called_once()

    @patch('telex_test_app.views.JiraReports')
    def test_jira_request_exception_handling(self, MockJiraReports):
        # Configure mock to raise exception
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.side_effect = requests.exceptions.RequestException("Connection error")

        # Execute view
        response = self.view(self.request)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('error', response.data)
        self.assertIn('Connection error', response.data['error'])

    @patch('telex_test_app.views.JiraReports')
    def test_general_exception_handling(self, MockJiraReports):
        # Configure mock to raise exception
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.side_effect = ValueError("Invalid data format")

        # Execute view
        response = self.view(self.request)

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.data)
        self.assertIn('Invalid data format', response.data['error'])

    @patch('telex_test_app.views.JiraReports')
    def test_date_range_calculation(self, MockJiraReports):
        # Configure mock
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.return_value = self.mock_issues
        mock_jira_instance.format_priority_counts.return_value = {}

        # Freeze time for testing
        current_date = datetime(2023, 5, 15)
        start_date = current_date - timedelta(days=7)

        with patch('telex_test_app.views.datetime') as mock_datetime:
            mock_datetime.now.return_value = current_date
            mock_datetime.timedelta = timedelta

            # Execute view
            response = self.view(self.request)

            # Assertions
            self.assertEqual(response.data['date_range']['start'], start_date.strftime('%B %d'))
            self.assertEqual(response.data['date_range']['end'], current_date.strftime('%B %d, %Y'))

    @patch('telex_test_app.views.JiraReports')
    def test_priority_breakdown_calculation(self, MockJiraReports):
        # Configure mock
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.return_value = self.mock_issues

        # Custom mock implementation for format_priority_counts
        def mock_format_priority(counts):
            return counts

        mock_jira_instance.format_priority_counts.side_effect = mock_format_priority

        # Execute view
        response = self.view(self.request)

        # Assertions
        self.assertEqual(response.data['priority_breakdown']['pending'], {'High': 2, 'Medium': 1})
        self.assertEqual(response.data['priority_breakdown']['resolved'], {'Low': 1, 'Medium': 1})

        # Verify format_priority_counts was called twice (once for pending, once for resolved)
        self.assertEqual(mock_jira_instance.format_priority_counts.call_count, 2)

    @patch('telex_test_app.views.JiraReports')
    def test_metrics_calculation(self, MockJiraReports):
        # Configure mock
        mock_jira_instance = MockJiraReports.return_value
        mock_jira_instance.get_weekly_issues.return_value = self.mock_issues
        mock_jira_instance.calculate_resolution_rate.return_value = "40%"
        mock_jira_instance.calculate_workload_index.return_value = "Moderate"

        # Execute view
        response = self.view(self.request)

        # Assertions
        self.assertEqual(response.data['metrics']['resolution_rate'], "40%")
        self.assertEqual(response.data['metrics']['workload_index'], "Moderate")

        # Verify calculation methods were called with correct arguments
        mock_jira_instance.calculate_resolution_rate.assert_called_once_with(3, 2)
        mock_jira_instance.calculate_workload_index.assert_called_once_with(3, 2)