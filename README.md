# OpenStudio(R) EE Measures 

EE measures used by OpenStudio(R). This contains general use energy efficiency measures. Some measures here may also be suitable for calibration or model articulation. Similarly, some measures in other measure gem repos may also be suitable for energy efficiency usage.


## Installation

Add this line to your application's Gemfile:

```ruby
gem 'openstudio-ee-measures'
```

And then execute:

    $ bundle

Or install it yourself as:

    $ gem install 'openstudio-ee-measures'

# Compatibility Matrix

|OpenStudio EE Gem|OpenStudio|Ruby|
|:--------------:|:----------:|:--------:|
| 0.12.0 | 3.10      | 3.2.2    |
| 0.11.1 | 3.9      | 3.2.2    |
| 0.10.0 | 3.8      | 3.2.2    |
| 0.9.0 | 3.7      | 2.7    |
| 0.8.0 | 3.6      | 2.7    |
| 0.7.0 | 3.5      | 2.7    |
| 0.6.0 | 3.4      | 2.7    |
| 0.5.0 | 3.3      | 2.7    |
| 0.4.0 | 3.2      | 2.7    |
| 0.3.0 - 0.3.2  | 3.1      | 2.5    |
| 0.2.0 - 0.2.1  | 3.0      | 2.5    |
| 0.1.0 | 2.9     | 2.2.4    |

# Contributing 

Please review the [OpenStudio Contribution Policy](https://openstudio.net/openstudio-contribution-policy) if you would like to contribute code to this gem.


# Releasing

* Update CHANGELOG.md
* Run `rake openstudio:rubocop:auto_correct`
* Run `rake openstudio:update_copyright`
* Run `rake openstudio:update_measures` (this has to be done last since prior tasks alter measure files)
* Update version in `readme.md`
* Review dependency versions in `openstudio-calibration-measures.gemspec` (especially openstudio-standards and openstudio-extension)
* Update version in `/lib/openstudio/ee-measures/version.rb`. Do not create a patch release if there are breaking changes or if this new version will support a biannual OpenStudio release; make a "minor" release instead. (ex: going from 0.7.0 to 0.8.0)
* Create PR to master, after tests and reviews complete, then merge
* Locally - from the master branch, run `rake release`
* On GitHub, go to the releases page and update the latest release tag. Name it “Version x.y.z” and copy the CHANGELOG entry into the description box.

