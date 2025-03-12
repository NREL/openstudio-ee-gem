import os
import unittest
import shutil
from pathlib import Path
import openstudio

class ExampleReportTest(unittest.TestCase):
    
    def is_openstudio_2(self):
        try:
            workflow = openstudio.WorkflowJSON()
            return True
        except:
            return False
    
    def model_in_path_default(self):
        return os.path.join(os.path.dirname(__file__), "ExampleModel.osm")
    
    def epw_path_default(self):
        epw = Path(os.path.join(os.path.dirname(__file__), "USA_CO_Golden-NREL.724666_TMY3.epw"))
        self.assertTrue(epw.exists())
        return str(epw)
    
    def run_dir(self, test_name):
        return os.path.join(os.path.dirname(__file__), "output", test_name)
    
    def model_out_path(self, test_name):
        return os.path.join(self.run_dir(test_name), "TestOutput.osm")
    
    def workspace_path(self, test_name):
        return os.path.join(self.run_dir(test_name), "run", "in.idf") if self.is_openstudio_2() else os.path.join(self.run_dir(test_name), "ModelToIdf", "in.idf")
    
    def sql_path(self, test_name):
        if self.is_openstudio_2():
            return os.path.join(self.run_dir(test_name), "run", "eplusout.sql")
        else:
            return os.path.join(self.run_dir(test_name), "ModelToIdf", "EnergyPlusPreProcess-0", "EnergyPlus-0", "eplusout.sql")
    
    def report_path(self, test_name):
        return os.path.join(self.run_dir(test_name), "report.html")
    
    def setup_test(self, test_name, idf_output_requests, model_in_path=None, epw_path=None):
        model_in_path = model_in_path or self.model_in_path_default()
        epw_path = epw_path or self.epw_path_default()
        
        os.makedirs(self.run_dir(test_name), exist_ok=True)
        self.assertTrue(os.path.exists(self.run_dir(test_name)))
        
        if os.path.exists(self.report_path(test_name)):
            os.remove(self.report_path(test_name))
        
        self.assertTrue(os.path.exists(model_in_path))
        
        if os.path.exists(self.model_out_path(test_name)):
            os.remove(self.model_out_path(test_name))
        
        workspace = openstudio.Workspace("Draft", "EnergyPlus")
        workspace.addObjects(idf_output_requests)
        
        rt = openstudio.energyplus.ReverseTranslator()
        request_model = rt.translateWorkspace(workspace)
        
        translator = openstudio.version. VersionTranslator()
        model = translator.loadModel(model_in_path)
        self.assertFalse(model.empty())
        model = model.get()
        model.addObjects(request_model.objects())
        model.save(self.model_out_path(test_name), True)
        
        if "OPENSTUDIO_TEST_NO_CACHE_SQLFILE" in os.environ and os.path.exists(self.sql_path(test_name)):
            os.remove(self.sql_path(test_name))
        
        self.setup_test_2(test_name, epw_path) if self.is_openstudio_2() else self.setup_test_1(test_name, epw_path)
    
    def test_good_argument_values(self):
        test_name = "test_good_argument_values"
        
        measure = ExampleReport()
        runner = openstudio.measure.OSRunner(openstudio.WorkflowJSON())
        
        arguments = measure.arguments()
        argument_map = openstudio.measure.convertOSArgumentVectorToMap(arguments)
        
        args_hash = {}
        for arg in arguments:
            temp_arg_var = arg.clone()
            if arg.name() in args_hash:
                self.assertTrue(temp_arg_var.setValue(args_hash[arg.name()]))
            argument_map[arg.name()] = temp_arg_var
        
        idf_output_requests = measure.energyPlusOutputRequests(runner, argument_map)
        self.assertEqual(0, len(idf_output_requests))
        
        epw_path = self.epw_path_default()
        self.setup_test(test_name, idf_output_requests)
        
        self.assertTrue(os.path.exists(self.model_out_path(test_name)))
        self.assertTrue(os.path.exists(self.sql_path(test_name)))
        self.assertTrue(os.path.exists(epw_path))
        
        runner.setLastOpenStudioModelPath(openstudio.path(self.model_out_path(test_name)))
        runner.setLastEnergyPlusWorkspacePath(openstudio.path(self.workspace_path(test_name)))
        runner.setLastEpwFilePath(openstudio.path(epw_path))
        runner.setLastEnergyPlusSqlFilePath(openstudio.path(self.sql_path(test_name)))
        
        if os.path.exists(self.report_path(test_name)):
            os.remove(self.report_path(test_name))
        self.assertFalse(os.path.exists(self.report_path(test_name)))
        
        start_dir = os.getcwd()
        try:
            os.chdir(self.run_dir(test_name))
            measure.run(runner, argument_map)
            result = runner.result()
            self.assertEqual("Success", result.value().valueName())
        finally:
            os.chdir(start_dir)
        
        self.assertTrue(os.path.exists(self.report_path(test_name)))

if __name__ == "__main__":
    unittest.main()
