import os
import json
import jinja2
from openstudio import measure  # Assuming OpenStudio bindings exist for Python
from resources import os_lib_reporting_example

class ExampleReport(measure.ReportingMeasure):
    def name(self):
        return "Example Report"

    def description(self):
        return (
            "Simple example of modular code to create tables and charts in OpenStudio reporting measures. "
            "This is not meant to use as is, it is an example to help with reporting measure development."
        )

    def modeler_description(self):
        return (
            "This measure uses the same framework and technologies (bootstrap and dimple) "
            "that the standard OpenStudio results report uses to create an HTML report with tables and charts. "
            "Download this measure and copy it to your Measures directory using PAT or the OpenStudio application. "
            "Then alter the data in os_lib_reporting_custom.py to suit your needs. Make new sections and tables as needed."
        )

    def possible_sections(self):
        result = []
        all_sections = [method for method in dir(os_lib_reporting_example) if "section" in method]
        method_locations = {
            method: getattr(os_lib_reporting_example, method).__code__.co_firstlineno for method in all_sections
        }
        result = [k for k, v in sorted(method_locations.items(), key=lambda item: item[1])]
        return result

    def arguments(self, model=None):
        args = []
        for method_name in self.possible_sections():
            arg = measure.OSArgument.makeBoolArgument(method_name, True)
            display_name = getattr(os_lib_reporting_example, method_name)(None, None, None, True)["title"]
            arg.setDisplayName(display_name)
            arg.setDefaultValue(True)
            args.append(arg)
        return args

    def energyPlusOutputRequests(self, runner, user_arguments):
        super().energyPlusOutputRequests(runner, user_arguments)
        return []

    def run(self, runner, user_arguments):
        super().run(runner, user_arguments)

        setup = os_lib_reporting_example.setup(runner)
        if not setup:
            return False
        
        model = setup["model"]
        sql_file = setup["sqlFile"]
        web_asset_path = setup["web_asset_path"]

        args = {str(k): v for k, v in runner.getArgumentValues(self.arguments(), user_arguments).items()}
        if not args:
            return False
        
        runner.registerInitialCondition("Gathering data from EnergyPlus SQL file and OSM model.")

        self.name = self.name()
        self.sections = []
        sections_made = 0

        for method_name in self.possible_sections():
            if not args.get(method_name, False):
                continue
            
            try:
                section = getattr(os_lib_reporting_example, method_name)(model, sql_file, runner, False)
                display_name = getattr(os_lib_reporting_example, method_name)(None, None, None, True)["title"]
                if section:
                    self.sections.append(section)
                    sections_made += 1
                    for table in section.get("tables", []):
                        if not table:
                            runner.registerWarning(f"A table in {display_name} section returned false and was skipped.")
                            section["messages"] = [f"One or more tables in {display_name} section returned false and was skipped."]
                else:
                    runner.registerWarning(f"{display_name} section returned false and was skipped.")
            except Exception as e:
                runner.registerWarning(f"{display_name} section failed and was skipped because: {str(e)}")
                self.sections.append({"title": display_name, "tables": [], "messages": [str(e)]})

        template_path = os.path.join(os.path.dirname(__file__), "resources", "report.html.j2")
        if not os.path.exists(template_path):
            template_path = os.path.join(os.path.dirname(__file__), "report.html.j2")
        
        with open(template_path, "r") as file:
            template_content = file.read()
        
        template = jinja2.Template(template_content)
        html_out = template.render(name=self.name, sections=self.sections)

        html_out_path = "./report.html"
        with open(html_out_path, "w") as file:
            file.write(html_out)

        sql_file.close()
        runner.registerFinalCondition(f"Generated report with {sections_made} sections to {html_out_path}.")
        return True

# Register with OpenStudio
ExampleReport().registerWithApplication()
