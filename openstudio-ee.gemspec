lib = File.expand_path('lib', __dir__)
$LOAD_PATH.unshift(lib) unless $LOAD_PATH.include?(lib)
require 'openstudio/ee_measures/version'

Gem::Specification.new do |spec|
  spec.name          = 'openstudio-ee'
  spec.version       = OpenStudio::EeMeasures::VERSION
  spec.authors       = ['David Goldwasser', 'Nicholas Long']
  spec.email         = ['david.goldwasser@nrel.gov', 'nicholas.long@nrel.gov']

  spec.homepage      = 'https://openstudio.net'
  spec.summary       = 'Library and measures for OpenStudio for energy efficiency use cases'
  spec.description   = 'Library and measures for OpenStudio for energy efficiency use cases'
  spec.metadata = {
      'bug_tracker_uri' => 'https://github.com/NREL/openstudio-ee-gem/issues',
      'changelog_uri' => 'https://github.com/NREL/openstudio-ee-gem/blob/develop/CHANGELOG.md',
      # 'documentation_uri' =>  'https://www.rubydoc.info/gems/openstudio-ee-gem/#{gem.version}',
      'source_code_uri' => "https://github.com/NREL/openstudio-ee-gem/tree/v#{spec.version}"
  }

  spec.files = `git ls-files -z`.split("\x0").reject do |f|
    f.match(%r{^(test|lib.measures.*tests|spec|features)/})
  end
  spec.bindir = 'exe'
  spec.executables = spec.files.grep(%r{^exe/}) { |f| File.basename(f) }
  spec.require_paths = ['lib']

  spec.required_ruby_version = '~> 3.2.2'

  spec.add_dependency 'bundler', '~> 2.4.10'
  spec.add_dependency 'openstudio-extension', '~> 0.9.1'
  spec.add_dependency 'openstudio-standards', '0.8.2'
  spec.add_dependency 'multipart-post', '2.4.0'

  spec.add_development_dependency 'rubocop', '1.50'
  spec.add_development_dependency 'rubocop-checkstyle_formatter', '0.6.0'
  spec.add_development_dependency 'rubocop-performance', '1.20.0'
  spec.add_development_dependency 'simplecov', '0.22.0'
  spec.add_development_dependency 'rake', '~> 13.0'
  spec.add_development_dependency 'rspec', '~> 3.9'
  spec.add_development_dependency 'octokit', '4.18.0' # for change logs
end
